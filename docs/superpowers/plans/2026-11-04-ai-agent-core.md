# AI Slice B — agent core & streamed chat turns

**Date:** 2026-11-04
**Scope:** PydanticAI agent, grounding prompt, typed read-only tools, and the visitor chat-turn
SSE route. Ordering tools, order cards, the handoff classifier, and rate limiting are explicitly
out of scope.

## Goal

A visitor can send one message through `POST /public/chat/{slug}/messages` and receive a grounded
assistant reply over SSE. The agent may search approved business information, search the exact
catalogue, or request a human handoff. It cannot set prices, mutate orders, or confirm payments.

## Tasks

- [x] Add `pydantic-ai[groq]` and a Groq model factory
  (`GROQ_API_KEY`, `GROQ_AGENT_MODEL`).
- [x] Add per-turn `AgentDeps`: DB session, merchant, conversation, optional embedding provider.
- [x] Add grounding prompt with merchant name/currency, tool rules, payment rules, and the
      `<buyer_message>` data boundary.
- [x] Add `search_business_info(query)` tool backed by hybrid RAG retrieval.
- [x] Add `search_catalogue(query, limit)` tool backed by tenant-scoped SQL over active products
      and variants, returning exact price/stock strings.
- [x] Add `request_handoff(reason)` tool backed by the conversation state machine.
- [x] Add streamed turn service:
  - load the last 20 customer/agent messages, capped at 4,000 chars each
  - stream `delta` and `tool_status`
  - persist the final `agent` message
  - emit `error` + `done` on failure
- [x] Add `POST /public/chat/{slug}/messages` with visitor-token auth:
  - `503` when `GROQ_API_KEY` is missing (before saving the customer message)
  - `409` when closed
  - save-only + `system` handoff notice when `handoff_requested` / `human_active`
- [x] Add tests with PydanticAI `TestModel` and a fake embedding provider.
- [x] Update `docs/ai.md`, `docs/architecture.md`, `docs/api/conversations.md`,
      `docs/contracts/sse.md`, `docs/status.md`, and the README.

## Files

```text
backend/app/agent/
├── agent.py          Groq model factory + PydanticAI agent builder
├── deps.py           AgentDeps dataclass
├── prompts.py        grounding rules + buyer-message wrapper
├── routes.py         POST /public/chat/{slug}/messages
├── schemas.py        ChatTurnIn
├── service.py        stream_turn + bounded history + persistence
└── tools/
    ├── business_info.py
    ├── catalogue.py
    └── handoff.py
```

## Verification

- Targeted agent tests: 13 passed after the model-default update.
- Full backend suite: **115 passed** on 2026-11-04 (29m 44s, Supabase-backed).
- Live Groq verification passed: the agent called `search_catalogue`, answered with the seeded
  exact price (`$25.00 USD`), and persisted the customer/agent messages. The temporary merchant
  used for the check was deleted.
- `bge-m3` is pulled in Ollama, but the installed Ollama runner is missing its `llama-server`
  binary, so live RAG still needs the local Ollama installation repaired.

## Follow-ups

1. Ordering tools: draft mutation, delivery-zone selection, confirmation, payment link.
2. `order_update` SSE events and order cards.
3. Handoff classifier and per-IP/per-conversation rate limits.
4. Prompt-injection and golden-path suites against a live model.
5. Gemini embedding failover and full reindex procedure.
