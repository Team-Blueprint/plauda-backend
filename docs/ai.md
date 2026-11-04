# Plauda AI — architecture & implementation notes

**Status:** Slice A (RAG foundation) is implemented and verified by the full backend suite
(102 tests passed). Agent turns are queued next.

This document is the readable companion to the AI sections of
[`BUILD_PLAN.md`](../BUILD_PLAN.md):

- §4 — agent runtime, tool registry, autonomy boundaries, handoff, grounding rules
- §5 — embeddings, vector index, provider failover
- §6.4 / §6.6 — recovery and refund guardrails
- §11 Phases 1–3 and 6 — build order and done criteria

The detailed task plan for the first slice is in
[`superpowers/plans/2026-11-02-ai-rag-foundation.md`](superpowers/plans/2026-11-02-ai-rag-foundation.md).

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
| **B. Agent core** | PydanticAI loop, prompt assembly, state-gated tool registry, TestModel tests |
| **C. Chat integration** | streaming visitor turns, tool status, order-card events, handoff classifier |
| **D. Ordering tools** | catalogue search, order draft operations, delivery, confirm, payment link |
| **E. Hardening** | Gemini failover/reindex, Groq limits, injection suite, golden path |

The first implementation plan covered **Slice A only**. Later slices get their own plans once A is
verified, because the agent should consume a retrieval interface that is already tested.

Implemented in Slice A:

- `app/rag/chunker.py` — overlapping whitespace-token chunks
- `app/rag/embedders/` — Cloudflare, Ollama, Gemini adapters and factory
- `app/rag/reindex.py` — atomic per-document replacement
- `app/rag/retrieval.py` — tenant-scoped hybrid ranking
- Migration `0006` — pgvector, `knowledge_chunks`, HNSW + GIN indexes
- `PUT /business-info/{source}` — best-effort reindex after save

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
| `gemini` | `gemini-embedding-001` | 1024 | backup / explicit switch |

Vector spaces are never mixed. Every row records its provider and model, and switching the active
provider requires a full reindex before search goes live.

### Retrieval

Hybrid search over one merchant's chunks:

- vector cosine top-8
- PostgreSQL full-text top-5
- weighted score: `0.7 * vector + 0.3 * text`
- returns chunk text, source, and score

The agent tool later wraps this as `search_business_info(query)`. It returns citations, not
instructions.

## Grounding invariants

- Buyer text is data, never instructions.
- The model cannot state a price, stock level, discount, or policy without a tool result.
- The model cannot mark an order paid, issue an uncapped refund, or write totals.
- Payment confirmation only comes from the verified PayPal webhook.
- If the answer is not in the data: say so and offer to relay to the seller.
- A human handoff is honored immediately.

## Local development

Default provider is `ollama_local`:

```bash
ollama pull bge-m3
```

Required keys for the hosted providers:

```text
CF_ACCOUNT_ID=
CF_API_TOKEN=
GEMINI_API_KEY=
GROQ_API_KEY=
```

`GROQ_API_KEY` is only needed when Slice B starts. RAG tests use deterministic mock embeddings, so
the foundation can be built and tested without hosted keys.

The database must have pgvector enabled:

```sql
create extension if not exists vector;
```

Migration `0006` does this, but the Supabase project must allow extension creation. It has been
applied to the dev database.

## What is still paused

- Refund flow
- Recovery worker
- Production deployment/hardening
- Agent and chat integration (Slice B onward)

Refunds and recovery are not prerequisites for Slice A. They remain in the Phase 5 backlog.
