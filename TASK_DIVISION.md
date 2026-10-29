# Plauda — Team Task Division

*Who builds what, in what order, and how the three tracks connect.*
Companion to `BUILD_PLAN.md` — phases (0–6) and task numbering refer to that file.

| | |
|---|---|
| Date | 2026-10-27 |
| Team | B = Backend dev · F = Frontend dev · M = ML (beginner-friendly track) |

---

## 1. Roles at a Glance

| Track | Owns | Folder ownership | Summary |
|---|---|---|---|
| **B — Backend** | Everything infra: auth, database/migrations, catalogue & orders services, PayPal adapter + webhooks, background workers, SSE plumbing, API contracts | `backend/app/{db,auth,merchants,orders,payments,conversations,workers}` + `agent/agent.py` & `agent/sse.py` skeletons | The system the agent and UI live inside |
| **F — Frontend** | The entire React app: dashboard (catalogue, business info, inbox, orders, settings) + public chat page + SSE client | `frontend/` | What merchants and buyers see |
| **M — ML** | Intelligence: RAG pipeline (chunk → embed → retrieve), agent prompts & tool behavior, handoff classifier, embeddings failover, evaluation & injection tests, golden-path E2E script | `backend/app/rag/` + `agent/{prompts,tools}/` + `backend/tests/agent*` | What makes Plauda smart and grounded |

**The clean seam between B and M:** *B builds the loop that streams; M decides what the loop says
and which tools it calls.* B scaffolds `agent.py` (PydanticAI wiring, SSE streaming, state-gated
tool filtering) and M fills in prompts, tool behavior, and quality. They pair on the seam at the
start of Phases 1 and 3.

---

## 2. Shared Contracts (build these FIRST — they unblock parallel work)

Everything the three tracks touch crosses one of these seams. Each has a single owner and lives
in the repo so PRs don't drift:

| Contract | Owner | Where | Unblocks |
|---|---|---|---|
| **REST API shape** (OpenAPI) | B (writes) → F consumes | `docs/contracts/openapi.json` (generated) | F builds all pages against it from day 1 |
| **SSE event schema** | B (with M) → F consumes | `docs/contracts/sse.md` | Chat page + inbox live updates |
| **Agent tool list & behavior** | M (defines) → B implements DB-backed bodies | `docs/contracts/agent-tools.md` | Phase 3 split |
| **Embedding provider interface** | M (owns) → B wires into tasks | `backend/app/rag/embedders/base.py` | Embed pipeline + failover |
| **Data model / enums** | B | Alembic migrations are the truth | Everyone |

**SSE event types (v1):**

```
delta         {"text": "..."}                       # agent token stream
tool_status   {"tool": "...", "state": "started|done", "label": "checking stock"}
order_update  {<order draft object>}                # live order card
system        {"kind": "receipt|handoff|payment|reminder", "text": "..."}
error         {"code": "rate_limited|grounding_fail|...", "message": "..."}
done          {}
```

**Embedding provider interface (M defines, day 1):**

```python
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dims(self) -> int: ...        # bge-m3 = 1024
    @property
    def name(self) -> str: ...        # recorded per chunk row
```

---

## 3. Phase-by-Phase Assignment

### Phase 0 — Foundations (~3–4 days)

| Owner | Tasks |
|---|---|
| **B** | Monorepo scaffold; `config.py`; Supabase project + `create extension vector;`; Alembic wired; merchants/users tables; JWT auth; `/healthz`; logging; CI (pytest + ruff); **publish OpenAPI + SSE + enums contracts** |
| **F** | Vite + TS + Tailwind scaffold; router shell; API client generated from B's OpenAPI; login/register pages against the contract (B's real auth lands mid-phase) |
| **M** | Keys checklist (§13 of BUILD_PLAN): Supabase, Groq, Cloudflare Workers AI, Gemini — one tiny verify script per key; **ramp-up micro-tasks (§4 below)**; write the one-page agent-loop summary from the spec |

### Phase 1 — Catalogue & RAG pipeline (~1 week)

| Owner | Tasks |
|---|---|
| **B** | Product/variant/delivery-zone CRUD; Supabase Storage image upload; merchant slug + `/public/chat/{slug}/meta`; settings endpoints; Procrastinate setup (polling mode vs Supabase); **pairs with M day 1–2 to wire the embed task** |
| **M** | Chunker (~400 tokens, overlap); CF `bge-m3` adapter; Gemini adapter (skeleton, used in Phase 6); Ollama local adapter (dev); embed task body; **hybrid retrieval service (pgvector + full-text) + its tests**; seed the demo merchant corpus |
| **F** | Catalogue UI (products table + editor drawer, variant rows, image upload); business-info markdown editors ×3 with save/reindex status; settings shell; chat-link copy button |

### Phase 2 — Grounded chat (~1–1.5 weeks)

| Owner | Tasks |
|---|---|
| **M** | System-prompt assembly (grounding contract §4.5); RAG answer mode; refusal behavior ("I'll check with the seller"); prompt-guard pre-filter; **agent tests with PydanticAI `TestModel`**: grounding, injection-as-data, off-brand → relay |
| **B** | Public chat API: conversation create, visitor token, `POST /messages` → SSE stream (streams M's agent); rate limiting (per IP + per conversation); input caps |
| **F** | Chat page `/chat/{slug}`: bubble UI, SSE client consuming all event types, tool-status chips, error/rate-limit UX, mobile-first pass |

### Phase 3 — Ordering & handoff (~1.5–2 weeks, the core phase)

| Owner | Tasks |
|---|---|
| **B** | Order model + state machine (`draft→confirmed`), server-side totals recomputation; **DB-backed implementations of M's tools** (catalogue search, order ops, delivery); inbox API (list, accept, staff reply, close, return-to-AI); state-gated tool filtering in `agent.py` |
| **M** | Agent tool registry & behavior contract (finalized with B in `agent-tools.md`); recommendation strategy (budget/preference → SQL query patterns); prompt v2 with order-draft + payment-status re-injection; handoff trigger A (phrase list) + trigger B (`llama-3.1-8b-instant` classifier) + "no staff available" honest path; state-machine agent tests |
| **F** | Inbox two-pane UI (conversation list via SSE + thread view); accept/reply/close/return controls; handoff-reason banner; order summary card live-updating from `order_update` events; "Talk to a human" button in chat |

### Phase 4 — PayPal (~1–1.5 weeks)

| Owner | Tasks |
|---|---|
| **B** | PayPal sandbox app; merchant credentials form (encrypted) + health check; `PaymentProvider` interface + Orders adapter; webhook endpoint (signature verify, `event_id` idempotency, state dispatch §6.3); `payment_actions` audit; webhook tests (forged signature, replay, declined capture) |
| **M** | `create_payment_link` tool gating behavior; receipt/reminder/notify message templates; the "never claim payment in words" prompt rules; chat copy for approve/cancel/expired states |
| **F** | Checkout-result routes (return/cancel from PayPal); payment status UI in chat + dashboard order views |

### Phase 5 — Recovery & dashboard (~1 week)

| Owner | Tasks |
|---|---|
| **B** | Procrastinate cron: reminder sweep (max 1, merchant toggle, timeout) + expiry sweep; orders/revenue/audit endpoints; refund flow with cap enforcement + over-cap approval task |
| **M** | Reminder & expiry message templates (one reminder rule, tone); recovery rate-limit rules; review of payment-state prompt rules against webhook reality |
| **F** | Orders page (status filters, detail, refund action, over-cap approval UI); revenue summary cards; audit-log view |

### Phase 6 — Failover & hardening (~1 week)

| Owner | Tasks |
|---|---|
| **M** | Gemini failover semantics (§5: new chunks flagged + reindex, never mixed spaces); reindex worker; **full injection suite**; **golden-path E2E demo script** (seed → chat → order → sandbox pay → dashboard sale) |
| **B** | Groq 429 handling (backoff/queue), per-merchant daily caps, prompt-caching prefix, security pass (CORS lockdown, JWT expiry, secrets hygiene) |
| **F** | Empty/error/loading states everywhere; provider-status display in settings; demo polish |

### Phase 7 — Backlog
Divided later when picked up. Natural owners: WhatsApp adapter = B, voice = M,
Disputes UI = F, partner onboarding = B.

---

## 4. M's Ramp-Up (Days 1–3, beginner-friendly, concrete)

Do these in order — each is a small finished artifact:

1. **Embeddings by hand** — install Ollama, `ollama pull bge-m3`, embed 5 sentences (2 similar,
   3 unrelated), compute cosine similarity in Python. *Artifact: a 30-line script.*
2. **pgvector hello-world** — in the Supabase SQL editor: create a table with `vector(1024)`,
   insert the 5 embeddings, run a top-5 similarity query. *Artifact: saved SQL + screenshot.*
3. **PydanticAI quickstart** — build a toy agent with 2 fake tools (`get_weather`, `get_time`)
   in a plain script; watch it decide which to call. *Artifact: `scratch/toy_agent.py`.*
4. **Read** Plauda spec §4–7 + BUILD_PLAN §4–6, then write a one-page summary of the agent loop
   and tool registry in your own words — post it in chat for B/F to correct. This becomes the
   first draft of `docs/contracts/agent-tools.md`.
5. **Verify the 4 API keys** with one tiny script each (§ Phase 0, M row).

Then pair with B on Phase 1's embed task. Everything after builds directly on these four skills.

---

## 5. Working Agreement

- **Git:** `main` protected; branches `p{phase}/{track}-{topic}` (e.g. `p2/ml-grounding-prompt`,
  `p3/fe-inbox`); every PR reviewed by one other teammate; contracts files may only change with
  the owner's sign-off.
- **Daily:** 15-min standup (done / next / blocked). **Weekly:** Monday plan, Friday demo —
  each phase's "done when" from BUILD_PLAN is demoed live, no exceptions.
- **Pairing points** (scheduled, don't skip): P1 day 1–2 (embed task seam), P2 day 1 (SSE stream
  through B's plumbing to F's client), P3 day 1 (tools contract), P4 day 1 (webhook payload walk).
- **When blocked > half a day:** bring it to standup, don't hero through it.

---

## 6. Rough Timeline (3 people, parallel)

| Week | Phase | Focus |
|---|---|---|
| 1 | 0 + start 1 | Contracts published; auth + scaffold + ramp-up done; catalogue started |
| 2 | 1 → 2 | Catalogue + RAG pipeline done; grounded chat live |
| 3–4 | 3 | Ordering + handoff — the core build |
| 5–6 | 4 | PayPal sandbox end-to-end |
| 7 | 5 | Recovery + dashboard |
| 8 | 6 | Failover, hardening, golden-path demo |

Buffers exist implicitly: Phase 3 is the longest and the critical path — if anything slips
elsewhere, protect Phase 3 by starting it on time even if Phase 2 polish is pending.
