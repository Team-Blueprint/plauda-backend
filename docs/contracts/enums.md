# Shared enums — Plauda v1

**Status:** v1 · **Owner:** backend · **Consumers:** frontend, agent, workers

These are the canonical string values stored in the database and returned by the API.
The UI should switch on these exact strings.

## User role — `users.role`

| Value | Meaning |
|---|---|
| `owner` | The single account per merchant in v1. Full access. |
| `staff` | Reserved for the backlog (staff accounts). Not created in v1. |

## Conversation status — `conversations.status`

| Value | Meaning |
|---|---|
| `ai` | AI is answering; agent turns enabled |
| `handoff_requested` | Handoff triggered, waiting for the owner to accept |
| `human_active` | Owner has taken over; AI turns suppressed |
| `closed` | Conversation finished |

## Message role — `messages.role`

| Value | Meaning |
|---|---|
| `customer` | Buyer text (always treated as data, never instructions) |
| `agent` | AI reply |
| `staff` | Human (owner) reply |
| `system` | System-generated (receipt, payment status, handoff notice) |
| `tool` | Tool call/result record |

## Order status — `orders.status`

| Value | Meaning | Written by |
|---|---|---|
| `draft` | Being built in chat | Agent tools |
| `confirmed` | Items + delivery complete; totals recomputed server-side | Agent tool `confirm_order` |
| `pending_payment` | PayPal approval link created | Agent tool `create_payment_link` |
| `paid` | Capture completed | **Webhook only** |
| `fulfilled` | Owner marked as delivered | Owner |
| `cancelled` | Cancelled by owner/customer flow | Owner / system |
| `expired` | Recovery sweep expired an unpaid order | Worker |

## Payment action — `payment_actions.action`

`create_link` · `refund` · `mark_paid` · `receipt` · `expire`

## Payment trigger — `payment_actions.trigger`

`agent` · `webhook` · `staff` · `system`

## Payment action result — `payment_actions.result`

| Value | Meaning |
|---|---|
| `success` | Action applied (link created, capture marked paid, refund recorded) |
| `declined` | PayPal reported a declined/failed capture; order unchanged |
| `ignored` | Event applied to nothing (unknown order, already-paid order, non-actionable event) |
| `failed` | Reserved for dispatch failures |

## Message metadata kind — `messages.meta.kind`

| Value | Meaning |
|---|---|
| `chat` | Ordinary grounded AI reply (`role="agent"`) |
| `handoff` | Handoff requested / owner joined / returned to AI / closed |
| `payment` | Payment received or declined notice |

## Channel — `conversations.channel`

`web` (v1). Backlog: `whatsapp`, `instagram`, `voice`.

## PayPal environment — `merchants.paypal_env`

`sandbox` · `live`

## Currency

Only **PayPal-supported currencies** are allowed. Initial allowlist (verify against PayPal's
current Orders API docs in Phase 4):

`AUD` `BRL` `CAD` `CHF` `CNY` `CZK` `DKK` `EUR` `GBP` `HKD` `HUF` `ILS` `JPY` `MXN` `MYR`
`NOK` `NZD` `PHP` `PLN` `SEK` `SGD` `THB` `TWD` `USD`

`NGN` and other unsupported codes must be rejected at catalogue/settings setup with a clear error.
