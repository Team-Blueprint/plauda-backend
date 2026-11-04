# Plauda AI — architecture & implementation notes

**Status:** Slices A (RAG foundation), B (agent core), C (chat integration), and D (ordering tools)
are implemented. The agent now answers from merchant data, builds and confirms orders through typed
tools, creates the merchant's PayPal approval link, emits live order cards, and hands off to a human
on explicit or classified escalation. Gemini-backed RAG, Groq chat, and the ordering flow are
live-verified.

This document is the readable companion to the AI sections of
[`BUILD_PLAN.md`](../BUILD_PLAN.md):

- §4 — agent runtime, tool registry, autonomy boundaries, handoff, grounding rules
- §5 — embeddings, vector index, provider failover
- §6.4 / §6.6 — recovery and refund guardrails
- §11 Phases 1–3 and 6 — build order and done criteria

The detailed task plans are:

- [`superpowers/plans/2026-11-02-ai-rag-foundation.md`](superpowers/plans/2026-11-02-ai-rag-foundation.md) — Slice A
- [`superpowers/plans/2026-11-04-ai-agent-core.md`](superpowers/plans/2026-11-04-ai-agent-core.md) — Slice B
- [`superpowers/plans/2026-11-04-ai-ordering-tools.md`](superpowers/plans/2026-11-04-ai-ordering-tools.md) — Slices C/D

## What the AI layer must do

1. Answer only from the merchant's approved business information and catalogue data.
2. Search products with SQL, never with vector similarity, so prices and stock are exact.
3. Build an order through typed, state-gated tools.
4. Create a PayPal link through the existing payment service — never touch payment state directly.
5. Hand off to a human on request, without arguing or stalling.
6. Stream the turn over SSE: `delta`, `tool_status`, `order_update`, `system`, `error`, `done`.

## Build order

| Slice | Deliverable |
|---|---|
| **A. RAG foundation** | ✅ `knowledge_chunks`, chunker, embedding adapters, reindex, hybrid retrieval |
| **B. Agent core** | ✅ PydanticAI loop, grounding prompt, typed tools, TestModel tests |
| **C. Chat integration** | ✅ streamed turns, live order cards, handoff classifier, rate limits |
| **D. Ordering tools** | ✅ catalogue search, draft/item/delivery/confirm, payment link |
| **E. Hardening** | Gemini failover/reindex, Groq limits, injection suite, golden path |

Slices A and B have their own implementation plans (linked above). Slice C/D work is recorded in
the ordering-tools plan.

Implemented in Slice A:

- `app/rag/chunker.py` — overlapping whitespace-token chunks
- `app/rag/embedders/` — Cloudflare, Ollama, Gemini adapters and factory
- `app/rag/reindex.py` — atomic per-document replacement
- `app/rag/retrieval.py` — tenant-scoped hybrid ranking
- Migration `0006` — pgvector, `knowledge_chunks`, HNSW + GIN indexes
- `PUT /business-info/{source}` — best-effort reindex after save

Implemented in Slice B:

- `app/agent/agent.py` — Groq model factory and PydanticAI agent builder
- `app/agent/prompts.py` — grounding rules and the `<buyer_message>` data boundary
- `app/agent/tools/` — business-info retrieval, catalogue SQL, and human handoff
- `app/agent/service.py` — streamed turn, bounded history, persistence, error events
- `POST /public/chat/{slug}/messages` — visitor turn over SSE
- `tests/test_agent_*.py` — prompt/config units, tool tests, turn persistence, route SSE

Implemented in Slice C:

- Per-IP and per-conversation sliding-window rate limits (`429` + `Retry-After`)
- Deterministic handoff phrase matching plus a fail-open Groq classifier
- `order_update` on the chat turn stream and on live conversation/owner streams
- Order-card serialization with decimal-string money values

Implemented in Slice D:

- `app/agent/tools/orders.py` — typed, state-gated order tools
- Current-order context injected into the system prompt on every turn
- Server-side variant stock checks at add and confirmation
- `create_payment_link` reuses the existing PayPal service with `trigger="agent"`
- Confirmed/pending orders cannot be edited or duplicated through chat

## Agent core

The agent runs through PydanticAI with a Groq model (`GROQ_AGENT_MODEL`, default
`openai/gpt-oss-120b`). The cheap classifier/utility model is `GROQ_CHEAP_MODEL`, default
`openai/gpt-oss-20b`. The agent is built per turn so the system prompt always reflects the current
merchant name and currency.

### Tools

| Tool | Data source | Boundary |
|---|---|---|
| `search_business_info(query)` | `app/rag/retrieval.py` hybrid search | Read-only, tenant-scoped, returns citations |
| `search_catalogue(query, limit)` | SQL over `products` / `product_variants` | Exact price/stock; only active products for this merchant |
| `start_order()` | `app/orders/service.create_draft` | One active order per conversation |
| `add_order_item(product_id, variant_id, qty)` | Catalogue + order service | Server checks tenant, active product, variant stock; creates a draft if needed |
| `remove_order_item(item_id)` | Order service | Draft orders only |
| `get_delivery_options()` | `delivery_zones` | Tenant-scoped fees, areas, and ETAs |
| `set_delivery_details(zone_id, address)` | Order service | Draft orders only; zone must belong to the merchant |
| `confirm_order()` | Order service | Recomputes live catalogue prices, stock, delivery fee, and totals |
| `create_payment_link()` | `app/payments/service` | Confirmed orders only; uses the merchant's PayPal app and `trigger="agent"` |
| `request_handoff(reason)` | `app/conversations/service.request_handoff` | Moves the thread to the owner inbox |

Products are deliberately **not** retrieved through the vector index. Similar-sounding text must
never be able to supply a price.

### Ordering flow

1. `search_catalogue` returns exact product/variant IDs, prices, and stock.
2. `add_order_item` creates a draft if needed. Products with variants require a variant ID so the
   stock check cannot be bypassed; a variant quantity above stock is rejected.
3. `get_delivery_options` lists the merchant's zones; `set_delivery_details` stores the chosen
   zone and address on the draft.
4. The model must summarize items, delivery fee, and the server-computed total and ask for explicit
   confirmation before calling `confirm_order`. The tool itself rejects confirmation unless the
   buyer's current message contains an explicit yes/confirm/place-order phrase, so the model cannot
   skip the approval step.
5. `confirm_order` reloads live product/variant and zone rows, recomputes subtotal, delivery fee,
   and total, and moves the order to `confirmed`.
6. `create_payment_link` calls the existing payment service with `trigger="agent"`, moving the
   order to `pending_payment` and returning the PayPal approval link.

Only draft orders can be edited. A confirmed, pending-payment, or paid order cannot be modified or
duplicated through chat. The owner can still cancel an eligible order from the dashboard.

Stock is validated at add and confirmation time but is **not reserved or decremented** in this
slice; the payment webhook remains the only paid transition.

### Chat safety

Before the agent runs, the chat route applies a shared sliding-window limit:

| Scope | Default | Config |
|---|---|---|
| Per client IP | 30 messages / 60s | `CHAT_RATE_LIMIT_PER_IP` |
| Per conversation | 12 messages / 60s | `CHAT_RATE_LIMIT_PER_CONVERSATION` |
| Window | 60s | `CHAT_RATE_LIMIT_WINDOW_SECONDS` |

Set either limit to `0` to disable that scope. Exceeding a limit returns HTTP `429` with a
`Retry-After` header before the customer message is saved. The limiter is in-process, matching the
SSE hub; replace it with a shared store before running multiple API instances.

Handoff has two layers:

1. Deterministic phrase matching for explicit requests such as “talk to a human” or “customer
   support”.
2. A fail-open cheap-model classifier (`HANDOFF_CLASSIFIER_ENABLED`, default on) for frustration,
   complaints, disputes, and out-of-scope requests.

If either layer decides to hand off, the customer message is persisted, the thread moves to
`handoff_requested`, a system message is added, and the turn streams the handoff notice without
calling the main agent. A provider timeout or error in the classifier logs a warning and continues
with the normal agent reply. `HANDOFF_CLASSIFIER_TIMEOUT_SECONDS` bounds the classifier call.

### Turn lifecycle

1. The route checks the store slug and the visitor token, then applies the rate limit.
2. In `ai` mode it resolves the Groq model; missing `GROQ_API_KEY` returns `503` before saving.
3. The customer message is persisted.
4. Explicit and model-assisted handoff checks run. A handoff ends the turn with a `system`
   notice plus `done`.
5. The agent receives the last 20 customer/agent messages, the current buyer text wrapped in
   `<buyer_message>`, the current server-owned order state, and the grounding/ordering prompt.
6. Text deltas stream as `delta`; tool calls emit `tool_status`. After an order-changing tool, the
   server reloads the order and emits `order_update` with a full replacement card.
7. The final assistant message is persisted, then `done` is emitted. Failures emit `error`
   followed by `done`.
8. In `handoff_requested` or `human_active`, the customer message is still saved and the stream
   emits a `system` handoff notice plus `done`; the AI does not run.

The agent is not given direct database or payment access beyond these typed tools.

## RAG design

### Indexed content

Only merchant-authored documents are embedded:

- `business_info_documents` (`about`, `policies`, `faq`)

Products are **not** embedded. Product search is SQL over name/description plus exact price and
variant rows. A similar-sounding product must never supply a price.

### Chunk shape

Each `knowledge_chunks` row stores:

- tenant (`merchant_id`) and source document
- `chunk_index`, text, token count
- 1024-dimension embedding
- embedding provider + model name
- generated `tsv` for full-text search

The chunker targets roughly 400 tokens with 50 tokens of overlap. The first implementation uses
whitespace-token approximation; exact tokenizer parity can be improved later without changing the
storage contract.

### Embedding providers

All adapters implement one interface:

```python
class EmbeddingProvider(Protocol):
    name: str
    model: str
    dims: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

| Provider | Model | Dimensions | Use |
|---|---|---|---|
| `cloudflare` | `@cf/baai/bge-m3` | 1024 | production primary |
| `ollama_local` | `bge-m3` | 1024 | local dev / no card |
| `gemini` | `gemini-embedding-001` | 1024 | backup / explicit switch; active in dev |

Vector spaces are never mixed. Every row records its provider and model, and switching the active
provider requires a full reindex before search goes live.

### Retrieval

Hybrid search over one merchant's chunks:

- vector cosine top-8
- PostgreSQL full-text top-5
- weighted score: `0.7 * vector + 0.3 * text`
- returns chunk text, source, and score

The agent tool wraps this as `search_business_info(query)`. It returns citations, not
instructions.

## Grounding invariants

- Buyer text is data, never instructions.
- The model cannot state a price, stock level, discount, or policy without a tool result.
- The model cannot mark an order paid, issue an uncapped refund, or write totals.
- Order tools resolve product, variant, zone, price, stock, and totals on the server; the model
  only supplies IDs, quantities, addresses, and intent.
- Payment confirmation only comes from the verified PayPal webhook.
- If the answer is not in the data: say so and offer to relay to the seller.
- A human handoff is honored immediately, including when the classifier requests it.

## Local development

The template default is `ollama_local`:

```bash
ollama pull bge-m3
```

This development machine currently uses Gemini (`EMBEDDING_PROVIDER=gemini`,
`gemini-embedding-001`, 1024 dimensions); Cloudflare Workers AI is also configured and verified.
The installed Ollama server is missing its `llama-server` binary, so it is optional. Every provider
uses a different vector space; switching requires reindexing all business-info documents before
retrieval.

Required keys for the hosted providers:

```text
CF_ACCOUNT_ID=
CF_API_TOKEN=
GEMINI_API_KEY=
GROQ_API_KEY=
```

`GROQ_API_KEY` is required for live agent turns and for the handoff classifier. Chat safety is
configured with `CHAT_RATE_LIMIT_PER_IP`, `CHAT_RATE_LIMIT_PER_CONVERSATION`,
`CHAT_RATE_LIMIT_WINDOW_SECONDS`, `HANDOFF_CLASSIFIER_ENABLED`, and
`HANDOFF_CLASSIFIER_TIMEOUT_SECONDS`. RAG and agent tests use deterministic mock embeddings and
PydanticAI test models, so the code can be built and tested without hosted keys. Live end-to-end
chat also needs a working embedding provider (`ollama pull bge-m3` for local dev, or
Cloudflare/Gemini credentials).

Gemini, Cloudflare, and Groq are verified live on this machine. Ollama remains optional; repair
its `llama-server` installation (or point `OLLAMA_BASE_URL` at a working instance) before using it.

The database must have pgvector enabled:

```sql
create extension if not exists vector;
```

Migration `0006` does this, but the Supabase project must allow extension creation. It has been
applied to the dev database.

## What is still paused

- Refund flow and recovery worker
- Production deployment/hardening
- Shared (multi-instance) rate limiting and durable handoff/queue infrastructure
- Gemini failover and the full prompt-injection/golden-path suite
- Stock reservation/decrement on payment

Refunds and recovery remain in the Phase 5 backlog. Slices A–D are built; Slice E hardening is
next. Live Groq chat, Gemini-backed RAG, and the ordering flow are verified.
