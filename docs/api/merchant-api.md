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
- `DELETE` → `204`. Products referenced by historical order items cannot be deleted (`409`) —
  deactivate them with `PATCH {"active": false}` instead.

### Variants

| Endpoint | Body | Result |
|---|---|---|
| `POST /products/{product_id}/variants` | `{name, options?, price_override?, stock?}` | `201` variant |
| `PATCH /products/{product_id}/variants/{variant_id}` | any subset | `200` variant |
| `DELETE /products/{product_id}/variants/{variant_id}` | — | `204` |

Variant rules: `name` 1–120; `options` arbitrary JSON object; `price_override` nullable decimal ≥ 0
(when null, the product price applies); `stock` integer ≥ 0. Sending `{"price_override": null}`
clears an override.

### Product images

#### `POST /products/{product_id}/images` → `201`

`multipart/form-data` with a single field named `file`.

```bash
curl -X POST "http://localhost:8000/products/$PRODUCT_ID/images" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@scarf.png;type=image/png"
```

- Allowed types: **JPEG, PNG, WebP, GIF**
- Max **5 MB** per file, max **5 images** per product
- Returns the **updated product** (with the new URL in `image_urls`)
- The image URL is public and directly renderable in `<img src>`

Errors: `413` too large · `422` unsupported type / image limit reached · `501` storage not
configured · `502` upstream storage failure.

#### `DELETE /products/{product_id}/images?url=…` → `204`

Removes the URL from `image_urls` and deletes the stored object. A deleted image may stay visible
via Supabase's CDN cache for a short while (expected). `404` if the URL is not on this product.

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

Upserts the document and reindexes it for AI retrieval. The response is returned even if the
embedding provider is unavailable; the previous chunks remain searchable and the save is not
rolled back. Re-save the document to retry indexing.

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

`paypal_connected` is read-only: true only when the merchant's PayPal client ID, secret, and webhook
ID are all saved (see [`payments.md`](payments.md)).

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
