# AI Slices C/D — chat integration, safety, and ordering tools

**Date:** 2026-11-04
**Scope:** live order cards, explicit/classified handoff, chat rate limits, and the typed ordering
tools that use the existing order and payment services. Refunds, recovery, deployment, and the
broader hardening suite remain out of scope.

## Goal

A visitor can build an order in chat: search the catalogue, add and remove items, choose delivery,
confirm, and receive a PayPal approval link. The server owns every price, stock check, delivery fee,
total, state transition, and payment-link call. The chat stream exposes the order as a replaceable
card, hands off to a human when needed, and refuses abusive message volume.

## Decisions

- The agent gets order IDs, variant IDs, quantities, and addresses — never prices or totals.
- `add_order_item` and `start_order` create a draft when the conversation has no active order.
- Draft orders are mutable; `confirmed`, `pending_payment`, and `paid` orders are not editable or
  duplicable through chat.
- A product with variants requires a variant ID so stock cannot be bypassed.
- `confirm_order` reloads catalogue and zone rows and recomputes all totals. It also rejects the
  call unless the buyer's current message explicitly confirms the pending summary.
- `create_payment_link` calls `create_payment_link_for_order(trigger="agent")`; the paid state is
  still written only by the verified PayPal webhook.
- Order cards use decimal strings and replace the whole client card.
- Handoff is deterministic first, then a fail-open cheap-model classifier.
- Rate limits are in-process (matching the SSE hub), configurable, and applied before the customer
  message is saved.
- Stock is validated but not reserved/decremented in this slice.

## Tasks

- [x] Serialize a full order card (`app/orders/cards.py`) and publish cards to the conversation and
      merchant hubs (`app/orders/events.py`).
- [x] Add `get_latest_order_for_conversation` and variant stock checks at add/confirm.
- [x] Add typed order tools:
  - `start_order`
  - `add_order_item`
  - `remove_order_item`
  - `get_delivery_options`
  - `set_delivery_details`
  - `confirm_order`
  - `create_payment_link`
- [x] Inject the current server-owned order state into the system prompt each turn.
- [x] Emit `order_update` after order-changing tools and when payment links or paid webhooks change
      an order.
- [x] Add deterministic handoff phrases and the cheap-model classifier with fail-open behavior.
- [x] Add per-IP and per-conversation sliding-window rate limits with `429` +
      `Retry-After`.
- [x] Publish order cards from the agent, owner payment-link endpoint, and paid webhook.
- [x] Add tests for order tools, stock/tenant/state gates, cards, streamed events, handoff,
      classifier routing, and rate limiting.
- [x] Update frontend docs and regenerate OpenAPI.

## Files

```text
backend/app/agent/
├── agent.py            order tool registration + cheap model factory
├── handoff.py          deterministic phrases + classifier
├── order_context.py    prompt/order summaries
├── rate_limit.py       sliding-window limiter
├── prompts.py          grounding + ordering rules + current order
├── routes.py           rate limit + handoff routing
├── service.py          order-card events in the turn stream
└── tools/orders.py     typed order tools

backend/app/orders/
├── cards.py            order-card serialization
├── events.py           live order-update publishing
└── service.py          latest-order lookup + stock checks

backend/app/payments/
├── service.py          publish after payment-link creation
└── webhooks.py         publish after paid webhook
```

## Verification

- Targeted tests: **27 passed** (`test_agent_config.py`, `test_agent_safety.py`,
  `test_agent_ordering.py`, `test_agent_api.py`, `test_agent_tools.py`, `test_agent_turn.py`).
- Full backend suite: **129 passed** on 2026-11-04 (offline units + Supabase-backed API tests).
- Live ordering flow: verified with Groq and Gemini RAG.
- `make openapi` and docs: updated and verified.
