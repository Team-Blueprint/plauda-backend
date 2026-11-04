# Orders API (dashboard)

**Status:** Phase 3 — complete. Orders originate in AI chat through typed, server-owned tools; the
dashboard reads orders and performs owner actions. The backend still owns all prices, stock checks,
delivery fees, totals, state transitions, and payment-link creation.

All endpoints require `Authorization: Bearer <token>` and only return the caller's orders.

## Status machine

| Status | Meaning | Written by |
|---|---|---|
| `draft` | Being built in chat | Order service |
| `confirmed` | Items + delivery complete; totals recomputed server-side | Order service |
| `pending_payment` | PayPal approval link created | Payments layer |
| `paid` | Capture completed | **Verified webhook only** |
| `fulfilled` | Owner marked as delivered | Owner |
| `cancelled` | Cancelled before payment | Owner / system |
| `expired` | Recovery sweep expired an unpaid order | Worker |

Allowed transitions:

```
draft → confirmed → pending_payment → paid → fulfilled
  ↓        ↓              ↓
cancelled cancelled   cancelled / expired
```

- `paid` can never be set through this API — only the verified PayPal webhook writes it.
- `fulfilled` requires `paid`.
- `cancelled` is allowed from `draft`, `confirmed`, or `pending_payment`.
- `fulfilled`, `cancelled`, and `expired` are terminal.

## Totals (server-owned)

At confirmation the backend recomputes everything from live data:

```
unit_price   = variant.price_override ?? product.price   (current catalogue row)
subtotal     = Σ(qty × unit_price)
delivery_fee = delivery_zone.fee                          (current zone row)
total        = subtotal + delivery_fee
```

`order_items` keeps `name_snapshot`, `variant_snapshot`, and `unit_price` so old orders render
correctly after catalogue edits. A product that is inactive at confirmation blocks the order
(`422`); a deleted product keeps its snapshot but cannot be reconfirmed.

Money is always a decimal **string** (`"60.50"`).

## Agent-driven ordering

The chat agent builds orders through these server-side tools:

| Tool | Effect |
|---|---|
| `start_order` | Creates one draft for the current conversation |
| `add_order_item` | Adds a product/variant; creates a draft if needed; enforces stock |
| `remove_order_item` | Removes a line from a draft |
| `get_delivery_options` | Lists merchant zones, areas, fees, and ETAs |
| `set_delivery_details` | Stores the chosen zone and address on a draft |
| `confirm_order` | Recomputes live prices/stock/delivery and moves to `confirmed` |
| `create_payment_link` | Creates/reuses the PayPal approval link for a confirmed order |

Safety rules enforced by the server, not the prompt:

- A product with variants requires a variant ID. The chosen variant must belong to that product
  and have enough stock for the requested total quantity.
- Variables and zones must belong to the same merchant as the order.
- Only draft orders can be edited. Confirmed, pending-payment, and paid orders cannot be modified or
  duplicated through chat.
- Prices, delivery fees, and totals are always reloaded from live catalogue/zone rows at
  confirmation; the model never supplies them.
- `confirm_order` is rejected unless the buyer's current message explicitly confirms (for example
  “yes”, “confirm”, or “place the order”).
- Payment links are only created for confirmed orders with a positive server-owned total.
- Stock is validated but not reserved or decremented in this slice.

The chat stream sends an `order_update` replacement card after each order-changing tool; the same
card is published to the visitor and owner live streams. See
[`../contracts/sse.md`](../contracts/sse.md).

## `GET /orders`

Query parameters:

| Name | Type | Default | Notes |
|---|---|---|---|
| `status` | enum | — | One of the statuses above; invalid values → `422` |
| `limit` | int | `50` | 1–100 |
| `offset` | int | `0` | ≥ 0 |

```json
{
  "items": [
    {
      "id": "3f1c…",
      "status": "confirmed",
      "currency": "USD",
      "total": "60.50",
      "item_count": 2,
      "created_at": "2026-10-29T19:00:00Z",
      "updated_at": "2026-10-29T19:02:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

`item_count` is the sum of quantities. Newest orders first.

## `GET /orders/{id}`

Full order:

| Field | Notes |
|---|---|
| `status`, `currency` | See above |
| `conversation_id`, `customer_id` | Links to the chat thread / visitor, or `null` |
| `subtotal`, `delivery_fee`, `total` | Null until confirmed |
| `delivery_details` | `{zone_id, zone_name, fee, eta_days, address}` — null until set |
| `paypal_order_id`, `approval_link` | Set when payment is requested |
| `reminder_count` | Recovery follow-ups sent (max 1) |
| `paid_at`, `expires_at` | Nullable timestamps |
| `items[]` | `id, product_id, variant_id, name_snapshot, variant_snapshot, qty, unit_price, line_total` |

`product_id` becomes `null` only if the product row is deleted at the database level; the snapshot
fields still render the line item. The dashboard cannot delete products with order history (`409`).

## `POST /orders/{id}/cancel`

Owner action. Allowed from `draft`, `confirmed`, or `pending_payment`. Returns the updated order.
`409` for any other current status.

## `POST /orders/{id}/fulfill`

Owner action. Allowed from `paid` only. Returns the updated order. `409` otherwise.

## `POST /orders/{id}/payment-link`

Owner action. Creates a PayPal Orders v2 checkout for a **confirmed** order and returns the updated
order with `status: "pending_payment"`, `paypal_order_id`, `approval_link`, and `expires_at`.

```json
{
  "id": "3f1c…",
  "status": "pending_payment",
  "currency": "USD",
  "total": "60.50",
  "paypal_order_id": "5O190127TN364715T",
  "approval_link": "https://www.sandbox.paypal.com/checkoutnow?token=…",
  "expires_at": "2026-11-01T19:00:00Z"
}
```

Idempotent while the order is `pending_payment`: calling again returns the existing link instead of
creating a second PayPal order.

| Status | Meaning |
|---|---|
| `200` | Link created, or existing link returned |
| `404` | Order not found or belongs to another merchant |
| `409` | Order is not `confirmed` (including draft, paid, cancelled, expired) |
| `422` | Order total is missing or not positive |
| `501` | Merchant has not connected PayPal |
| `502` | PayPal rejected or failed the order creation |

The link is what the chat/dashboard shows to the buyer. Payment is still confirmed **only** by the
verified `PAYMENT.CAPTURE.COMPLETED` webhook; this endpoint never marks an order paid.

## Not built yet

- `POST /orders/{id}/refund` and over-cap approval — Phase 5 (the PayPal refund adapter + webhook
  audit already exist).
- Creating orders manually from the dashboard — orders originate in chat through the agent tools.
- Stock reservation/decrement and recovery reminders/expiry — later work.
