# Merchant API — Phase 1 (catalogue & store config)

All endpoints require `Authorization: Bearer <token>` **except** `GET /public/chat/{slug}/meta`.
Money is always a decimal string (`"25.00"`). IDs are UUIDs. All resources are tenant-scoped:
another merchant's resource returns `404`, never `403`.

---

## Products

### `GET /products?include_inactive=false`

Returns the store's products, newest first. Inactive products are excluded unless
`include_inactive=true`.

```json
[
  {
    "id": "6c2a…",
    "name": "Silk scarf",
    "description": "Hand-dyed silk scarf",
    "price": "25.00",
    "currency": "USD",
    "active": true,
    "image_urls": ["https://example.com/scarf.jpg"],
    "created_at": "2026-10-29T19:30:00+00:00",
    "updated_at": "2026-10-29T19:30:00+00:00",
    "variants": [
      {
        "id": "0d5c…",
        "name": "Red",
        "options": {"color": "red"},
        "price_override": null,
        "stock": 4
      }
    ]
  }
]
```

### `POST /products` → `201`

```json
{
  "name": "Silk scarf",
  "description": "Hand-dyed silk scarf",
  "price": "25.00",
  "currency": "USD",
  "active": true,
  "image_urls": ["https://example.com/scarf.jpg"],
  "variants": [
    { "name": "Red", "options": {"color": "red"}, "price_override": null, "stock": 4 }
  ]
}
```

| Field | Rules |
|---|---|
| `name` | 1–200 chars |
| `description` | free text, default `""` |
| `price` | decimal > 0, 2 places |
| `currency` | optional; defaults to the store currency. Must equal store currency and be PayPal-supported. `NGN` → `422` |
| `active` | default `true` |
| `image_urls` | max **5** URLs |
| `variants` | optional nested list (same shape as the variant endpoints) |

### `GET /products/{product_id}` · `PATCH /products/{product_id}` · `DELETE /products/{product_id}`

- `PATCH` accepts any subset of `name`, `description`, `price`, `currency`, `active`,
  `image_urls`. Null values are ignored.
- `DELETE` → `204`. Hard delete today; Phase 3 will return `409` for products referenced by
  historical order items (deactivate instead).

### Variants

| Endpoint | Body | Result |
|---|---|---|
| `POST /products/{product_id}/variants` | `{name, options?, price_override?, stock?}` | `201` variant |
| `PATCH /products/{product_id}/variants/{variant_id}` | any subset | `200` variant |
| `DELETE /products/{product_id}/variants/{variant_id}` | — | `204` |

Variant rules: `name` 1–120; `options` arbitrary JSON object; `price_override` nullable decimal ≥ 0
(when null, the product price applies); `stock` integer ≥ 0. Sending `{"price_override": null}`
clears an override.

---

## Delivery zones

### `GET /delivery-zones`

```json
[
  {
    "id": "9f1c…",
    "name": "Lagos Mainland",
    "areas": ["Yaba", "Surulere"],
    "fee": "5.50",
    "eta_days": 2,
    "created_at": "…",
    "updated_at": "…"
  }
]
```

### `POST /delivery-zones` → `201`

```json
{ "name": "Lagos Mainland", "areas": ["Yaba", "Surulere"], "fee": "5.50", "eta_days": 2 }
```

| Field | Rules |
|---|---|
| `name` | 1–120 chars |
| `areas` | list of strings |
| `fee` | decimal ≥ 0 |
| `eta_days` | 0–365 |

`GET/PATCH/DELETE /delivery-zones/{zone_id}` follow the same pattern; `DELETE` → `204`.

---

## Business info (markdown)

### `GET /business-info`

Always returns exactly three documents; missing ones have empty content:

```json
[
  { "source": "about",    "content": "# About\n\nWe sell…", "updated_at": "…" },
  { "source": "policies", "content": "",                    "updated_at": null },
  { "source": "faq",      "content": "",                    "updated_at": null }
]
```

### `PUT /business-info/{source}` → `200`

`source` is one of `about`, `policies`, `faq` (anything else → `422`).

```json
{ "content": "# About\n\nWe sell hand-dyed silk." }
```

Upserts the document. Chunking + embedding (RAG index) is wired in the AI phase; until then,
saving only stores the markdown.

---

## Settings

### `GET /settings`

```json
{
  "name": "Ada's Closet",
  "slug": "ada-s-closet",
  "currency": "USD",
  "refund_cap": "0.00",
  "recovery_reminder_enabled": true,
  "recovery_timeout_minutes": 120,
  "paypal_connected": false,
  "chat_link": "http://localhost:5173/chat/ada-s-closet"
}
```

### `PATCH /settings`

```json
{
  "currency": "USD",
  "refund_cap": "50.00",
  "recovery_reminder_enabled": false,
  "recovery_timeout_minutes": 90
}
```

| Field | Rules |
|---|---|
| `currency` | PayPal-supported; must match the store. Changing it while products exist → `409` |
| `refund_cap` | decimal ≥ 0 |
| `recovery_timeout_minutes` | 15–10080 |
| `recovery_reminder_enabled` | boolean |

`paypal_connected` is read-only (becomes true in Phase 4 when credentials are saved).

---

## Public store meta (no auth)

### `GET /public/chat/{slug}/meta`

```json
{
  "name": "Ada's Closet",
  "slug": "ada-s-closet",
  "currency": "USD",
  "chat_link": "http://localhost:5173/chat/ada-s-closet"
}
```

`404` if the slug does not exist. This is what the public chat page calls before rendering.

---

## Error reference

| Code | When |
|---|---|
| `401` | Missing/invalid token on protected endpoints |
| `404` | Unknown ID, or a resource owned by another merchant |
| `409` | Currency change blocked by existing products |
| `422` | Validation failure (bad currency, negative money, >5 images, unknown source) |
