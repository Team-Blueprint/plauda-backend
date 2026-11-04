# Plauda AI — architecture & implementation notes

**Status:** Slice A (RAG foundation) is implemented and verified. Slice B (agent core) is
implemented, covered by 13 targeted tests, live-verified against Groq with real catalogue and
Gemini-backed RAG tool calls, and verified by the full backend suite (**115 tests passed**,
2026-11-04). Ordering tools are queued next.

This document is the readable companion to the AI sections of
[`BUILD_PLAN.md`](../BUILD_PLAN.md):

- §4 — agent runtime, tool registry, autonomy boundaries, handoff, grounding rules
- §5 — embeddings, vector index, provider failover
- §6.4 / §6.6 — recovery and refund guardrails
- §11 Phases 1–3 and 6 — build order and done criteria

The detailed task plans are:

- [`superpowers/plans/2026-11-02-ai-rag-foundation.md`](superpowers/plans/2026-11-02-ai-rag-foundation.md) — Slice A
- [`superpowers/plans/2026-11-04-ai-agent-core.md`](superpowers/plans/2026-11-04-ai-agent-core.md) — Slice B

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
| **C. Chat integration** | 🔨 streamed visitor turns + tool status done; order cards, handoff classifier, rate limits next |
| **D. Ordering tools** | catalogue search ✅; order draft operations, delivery, confirm, payment link next |
| **E. Hardening** | Gemini failover/reindex, Groq limits, injection suite, golden path |

Slices A and B have their own implementation plans (linked above). Slice C/D work will get a new
plan once the agent tools and chat event contract are settled.

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
| `request_handoff(reason)` | `app/conversations/service.request_handoff` | Moves the thread to the owner inbox |

Products are deliberately **not** retrieved through the vector index. Similar-sounding text must
never be able to supply a price.

### Turn lifecycle

1. The route checks the store slug and the visitor token.
2. In `ai` mode it resolves the Groq model; missing `GROQ_API_KEY` returns `503` before saving.
3. The customer message is persisted.
4. The agent receives the last 20 customer/agent messages, the current buyer text wrapped in
   `<buyer_message>`, and a prompt containing the hard grounding rules.
5. Text deltas stream as `delta`; tool calls emit `tool_status`; failures emit `error`; the final
   assistant message is persisted and then `done` is emitted.
6. In `handoff_requested` or `human_active`, the customer message is still saved and the stream
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
- Payment confirmation only comes from the verified PayPal webhook.
- If the answer is not in the data: say so and offer to relay to the seller.
- A human handoff is honored immediately.

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

`GROQ_API_KEY` is required for live agent turns. RAG and agent tests use deterministic mock
embeddings and PydanticAI `TestModel`, so the code can be built and tested without hosted keys.
Live end-to-end chat also needs a working embedding provider (`ollama pull bge-m3` for local dev,
or Cloudflare/Gemini credentials).

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
- Ordering tools (order drafts, delivery selection, confirm, payment link)
- Order-card `order_update` events, handoff classifier, per-IP/per-conversation rate limits
- Gemini failover and the full prompt-injection/golden-path suite

Refunds and recovery remain in the Phase 5 backlog. The agent core is stable enough to build
ordering tools on next. Live Groq turns and Gemini-backed RAG are verified.
