# Build status

Last updated: 2026-11-05

## Phase 0 — Foundations (backend) — ✅ complete

| Task | Status |
|---|---|
| Monorepo scaffold: `backend/` with uv, FastAPI, ruff, pytest | ✅ |
| `config.py` (pydantic-settings) + `.env.example` with every key | ✅ |
| SQLAlchemy 2.0 async engine + Supabase pooler handling (SSL, statement cache) | ✅ |
| Alembic wired (async) + migration `0001` (merchants, users) | ✅ |
| JWT auth: `POST /auth/register`, `POST /auth/login`, `GET /auth/me` (bcrypt + jose) | ✅ |
| CORS, `/healthz`, JSON structured logging, error handlers | ✅ |
| Tests: security units, healthz, auth API | ✅ |
| CI: ruff + format check + pytest | ✅ |
| Contracts for frontend: `openapi.json`, `sse.md`, `enums.md`, API guides | ✅ |
| Migration `0001` applied to Supabase | ✅ |
| Live HTTP verification: `/healthz` (db ok), register → login → me | ✅ 2026-10-29 |

**Done when:** register/login works against Supabase; migrations apply cleanly from an empty DB;
health check green. — ✅ **All verified.**

> Dev note: this network intercepts TLS, so `backend/.env` uses `DATABASE_SSL_MODE=require`
> (encrypted, no certificate verification). The default stays `verify-full`; switch back on a
> normal network.

## Phase 1 — Catalogue & RAG — ✅ complete

| Task | Status |
|---|---|
| Products + variants CRUD (tenant-scoped, PayPal currency rules, max 5 images) | ✅ |
| Delivery zones CRUD | ✅ |
| Business info markdown storage (`about` / `policies` / `faq`) | ✅ storage + best-effort reindex |
| Store settings (currency, refund cap, recovery toggle/timeout) | ✅ |
| Public store meta `GET /public/chat/{slug}/meta` (no auth) | ✅ |
| Product image upload → Supabase Storage (`POST/DELETE /products/{id}/images`) | ✅ live-verified |
| Migration `0002` (products, variants, zones, business info, pg_trgm) | ✅ |
| Migration `0006` (pgvector, `knowledge_chunks`, HNSW + GIN indexes) | ✅ applied |
| **RAG: chunker, CF/Ollama/Gemini adapters, atomic reindex, hybrid retrieval** | ✅ 26 tests |
| `PUT /business-info/{source}` reindexes after save; provider outage keeps old chunks | ✅ 2 tests |
| Tests: catalogue, variants, zones, business info, settings, public meta, storage | ✅ |
| Procrastinate worker setup | ⏸ deferred until worker tasks begin |

## Phase 2 — Grounded chat / conversations — ✅ complete (hardening continues in Phase 6)

| Task | Status |
|---|---|
| Migration `0004`: `customers`, `conversations`, `messages`, order FKs | ✅ applied |
| Visitor thread creation (`POST /public/chat/{slug}/conversations`) | ✅ |
| Visitor token: returned raw once, SHA-256 hash stored, bearer auth | ✅ |
| Public history + visitor message + handoff button endpoints | ✅ |
| Owner inbox: list/detail/history/accept/reply/return-to-ai/close | ✅ |
| Conversation status machine (`ai → handoff_requested → human_active → closed`, `human_active → ai`) | ✅ |
| In-process SSE hub + visitor/inbox streams (`message`, `conversation_update`) | ✅ |
| Tests: token isolation, handoff lifecycle, tenant scoping, pagination, order link, SSE hub | ✅ 9 pass |
| PydanticAI agent core + Groq model factory + grounding prompt | ✅ 6 tests |
| Typed tools: business-info retrieval, catalogue SQL, human handoff | ✅ 3 tests |
| Streamed agent turn: deltas, tool status, history, persistence, `done`/`error` | ✅ 1 test |
| `POST /public/chat/{slug}/messages` SSE route + human-mode bypass + 503 config guard | ✅ 3 tests |
| Per-IP/per-conversation rate limits, order-card events, handoff classifier | ✅ implemented + tested |

## Phase 3 — Ordering & handoff — ✅ complete

| Task | Status |
|---|---|
| Order draft model + state machine (`draft → confirmed`, totals recomputed server-side) | ✅ |
| Orders API: `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel`, `POST /orders/{id}/fulfill` | ✅ |
| `paid` webhook-only invariant + `pending_payment`/`paid`/`fulfill`/`expire` service paths | ✅ |
| Product delete guard for order history (`409`) | ✅ |
| Migration `0003` (orders, order_items, status check, recovery index) | ✅ applied |
| Tests: state machine, totals recomputation, merge, lifecycle, tenant scoping | ✅ 10 pass |
| **PydanticAI agent + tool registry** | ✅ agent core + business-info/catalogue/handoff tools |
| **Order tools wired into chat (`start_order` … `create_payment_link`)** | ✅ implemented + tested |
| Current-order prompt context + live `order_update` cards | ✅ |
| Variant stock validation at add and confirmation | ✅ |
| Agent uses existing PayPal service (`trigger="agent"`) and paid webhook publishes card | ✅ |

## Phase 4 — PayPal — ✅ complete

| Task | Status |
|---|---|
| Migration `0005`: `paypal_webhook_events`, `payment_actions`, `merchants.paypal_webhook_id_enc` | ✅ applied |
| Fernet credential encryption (`CREDENTIAL_ENCRYPTION_KEY`) | ✅ |
| `GET/POST/DELETE /settings/paypal` + OAuth credential health check | ✅ |
| Orders v2 adapter: create/get/capture/refund (httpx, no SDK) | ✅ mock-tested |
| Webhook endpoint: signature verification + `event_id` idempotency + audit ledger | ✅ mock-tested |
| `CHECKOUT.ORDER.APPROVED` → server-side capture (retry-safe) | ✅ mock-tested |
| `PAYMENT.CAPTURE.COMPLETED` → `paid` + audit + chat receipt | ✅ mock-tested |
| Declined capture handling (buyer notice) + refund webhook audit | ✅ declined mock-tested |
| Internal `create_payment_link_for_order` service | ✅ mock-tested |
| Owner `POST /orders/{id}/payment-link` (idempotent, tenant-scoped) | ✅ 3 tests |
| Tests: crypto, adapter, settings, webhook idempotency/rejection, declined notice, link creation | ✅ 20 pass |
| **Live sandbox payment + webhook verification** | ✅ paid 2026-11-02; capture `1EA58572KJ470073T` completed for USD 10.00; webhook signatures verified |
| **Owner refund endpoint + over-cap approval** | ⏸ Phase 5 |

## Phase 5 — Recovery & operations — 🔨 dashboard + audit done, recovery paused

| Task | Status |
|---|---|
| Orders list/detail + conversation history APIs | ✅ earlier phases |
| `GET /dashboard/summary`: today's revenue, orders, live chats | ✅ 2 tests |
| `GET /audit`: filtered, paginated payment audit trail | ✅ 2 tests |
| Owner refund endpoint + over-cap approval | ⏸ next |
| Recovery worker + reminder/expiry jobs | ⏸ paused by request |
| Reminder tests: exactly one reminder then expiry; toggle off = silence | ⏸ paused |

## Phase 6 — Failover & hardening — ⏸ not started

## Production deployment — ✅ live

| Task | Status |
|---|---|
| FastAPI Cloud app `plauda` (`backend/` as app directory) | ✅ deployed 2026-11-05 |
| API + health check | ✅ <https://plauda.fastapicloud.dev/healthz> → `db: ok` |
| Production env vars in FastAPI Cloud (secrets marked) | ✅ set from local `.env` |
| `APP_BASE_URL` / `FRONTEND_BASE_URL` | ✅ API URL + <https://plauda.vercel.app> |
| CORS preflight from the Vercel origin | ✅ `200` with `allow-origin: https://plauda.vercel.app` |
| `/public/chat/plauda-store/meta` | ✅ returns `chat_link` with the Vercel domain |
| PayPal webhook URL | ⏳ update in the PayPal dashboard (see [`deployment.md`](deployment.md)) |
| CI deploy workflow (`fastapi cloud setup-ci`) | ⏸ optional |

## Test suite

Full backend suite: **129 tests passed** on 2026-11-04 (offline units + Supabase-backed API tests),
including **27 targeted agent, safety, and ordering tests**. Runtime is ~30 min because every DB
test round-trips to Supabase.

## Open items

| Item | Owner | Notes |
|---|---|---|
| PayPal sandbox credentials | ✅ connected | New sandbox app + webhook stored for `plauda-store`; rotate the secret after testing |
| PayPal sandbox buyer account | ✅ ready | Sandbox personal/buyer login available for the checkout test |
| Public HTTPS URL for webhooks | ✅ deployed | `https://plauda.fastapicloud.dev/webhooks/paypal/{merchant_id}`; update the PayPal dashboard URL (ngrok no longer needed) |
| Frontend repo/location | Frontend dev | Contracts in `docs/contracts/` are ready |
| Domain for `plauda.app` links | You | Open question in BUILD_PLAN §16 |
| AI build | You | ✅ RAG foundation, agent core, chat safety, and ordering tools done 2026-11-04; live Groq catalogue, Gemini RAG, and ordering flow verified; hardening is next |
| `GROQ_API_KEY` | You | ✅ configured in gitignored `backend/.env`; live turns use `openai/gpt-oss-120b` |
| Rotate Groq API key | You (recommended) | The key was shared in chat; rotate it after local verification and update `backend/.env` |
| Embedding provider | You | ✅ Gemini `gemini-embedding-001` configured and live-verified; this is the active provider |
| Cloudflare backup | You | ✅ Workers AI `@cf/baai/bge-m3` configured and verified; switching back requires a full reindex |
| Local Ollama | You (optional) | `bge-m3` is pulled, but the installed Ollama runner is missing `llama-server`; repair it only if you want offline embeddings |
| Recovery worker | You | Paused by request; dashboard + audit are done |
| Rotate Supabase DB password | You (optional) | The dev connection string was shared in chat; it is only in gitignored `.env` |
