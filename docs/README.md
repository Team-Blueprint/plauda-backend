# Plauda — Documentation

Everything the frontend dev (or a future teammate) needs to integrate with the backend.
Start here, then open the file for your task.

| Document | What it covers | Audience |
|---|---|---|
| [`api/conventions.md`](api/conventions.md) | Base URL, auth header, error format, IDs, money, timestamps, CORS | Frontend |
| [`api/auth.md`](api/auth.md) | Register / login / me — full request & response reference | Frontend |
| [`api/merchant-api.md`](api/merchant-api.md) | Products, variants, delivery zones, business info, settings, public store meta | Frontend |
| [`api/orders.md`](api/orders.md) | Orders list/detail, status machine, totals, payment link, cancel & fulfill | Frontend |
| [`api/conversations.md`](api/conversations.md) | Visitor threads/messages, handoff, owner inbox, live streams | Frontend |
| [`api/payments.md`](api/payments.md) | PayPal setup, webhooks, payment links, audit | Frontend + backend |
| [`api/dashboard.md`](api/dashboard.md) | Revenue/order/chat summary and paginated payment audit trail | Frontend |
| [`contracts/openapi.json`](contracts/openapi.json) | Machine-readable REST surface (generated from the app) | Frontend (codegen) |
| [`contracts/sse.md`](contracts/sse.md) | Chat turn stream (`delta`, `tool_status`, `order_update`, `system`, `error`, `done`) + live conversation/inbox events | Frontend (chat + inbox) |
| [`contracts/enums.md`](contracts/enums.md) | Canonical status/role strings used by API + UI | Frontend + backend |
| [`ai.md`](ai.md) | AI architecture, RAG/agent plan, grounding rules, build order | Backend + AI |
| [`architecture.md`](architecture.md) | Backend stack, module layout, DB schema, multi-tenancy, env config, conventions | Backend + AI |
| [`status.md`](status.md) | Phase tracker — what is built, what is next, what is blocked | Everyone |
| [`deployment.md`](deployment.md) | FastAPI Cloud deployment, production env vars, health checks, PayPal webhook URL | Backend |

## How contracts stay in sync

`docs/contracts/openapi.json` is generated from the running FastAPI app:

```bash
make openapi   # from repo root
```

The backend regenerates it at the end of every phase. `sse.md` and `enums.md` are edited by hand
whenever the contract changes — treat them as reviewed API changes, not scratch notes.

## Ground rules for consumers

- The **OpenAPI file is the source of truth** for endpoints, request bodies, and response shapes.
- The API is versioned by phase, not by URL: paths are stable once published in a phase; additions
  are backward compatible.
- Money is always a decimal **string**; never parse it as a float in the UI.
- IDs are UUIDs (strings).
- Timestamps are ISO-8601 UTC.
