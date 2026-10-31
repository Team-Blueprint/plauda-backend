# Orders API (dashboard)

**Status:** Phase 3 backend foundation — complete. Order creation is owned by the backend order
service (agent tools will call it when AI work resumes); the dashboard reads orders and performs
owner actions.

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

## Not built yet

- `POST /orders/{id}/refund` and over-cap approval — Phase 5 (the PayPal refund adapter + webhook
  audit already exist).
- Creating orders from the dashboard — orders originate in chat (agent tools, paused with AI).
- The `create_payment_link` agent tool — the internal payment service is ready; see
  [`payments.md`](payments.md).
