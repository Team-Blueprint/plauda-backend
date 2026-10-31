# PayPal payments

**Status:** Phase 4 backend — complete with mocked PayPal calls. Live sandbox verification is
pending merchant sandbox credentials (client ID, secret, webhook ID).

Plauda never touches card data: buyers approve payment on PayPal, and the **verified webhook** is
the only path that marks an order `paid`.

## Connect a merchant account

Merchant PayPal credentials are stored **encrypted at rest** (Fernet,
`CREDENTIAL_ENCRYPTION_KEY`). The API never returns them.

### `GET /settings/paypal`

```json
{"connected": true, "env": "sandbox"}
```

`connected` is true only when client ID, secret, and webhook ID are all stored.

### `POST /settings/paypal`

```json
{
  "client_id": "AeA1…",
  "client_secret": "EL…",
  "webhook_id": "WH-…",
  "env": "sandbox"
}
```

Before saving, the backend performs a PayPal OAuth `client_credentials` check. Bad credentials →
`422`; nothing is stored. Success → `{"connected": true, "env": "sandbox"}`.

Where to get the values: PayPal Developer Dashboard → **Apps & Credentials** → your REST app →
client ID/secret. The **webhook ID** comes from the same app's **Webhooks** section.

### `DELETE /settings/paypal`

Clears all stored PayPal values (`204`). Existing orders keep their PayPal IDs for audit; new
payment requests fail until the merchant reconnects.

### Webhook URL to register with PayPal

```
{APP_BASE_URL}/webhooks/paypal/{merchant_id}
```

`APP_BASE_URL` must be publicly reachable over HTTPS (use a tunnel such as ngrok in development).
Register the events:

| Event | Handled |
|---|---|
| `CHECKOUT.ORDER.APPROVED` | ✅ captures the approved order (order stays `pending_payment` until `capture.completed`) |
| `PAYMENT.CAPTURE.COMPLETED` | ✅ marks the order `paid`, writes audit + chat receipt |
| `PAYMENT.CAPTURE.DECLINED` / `PAYMENT.CAPTURE.DENIED` | ✅ audit + chat “payment declined” notice |
| `PAYMENT.CAPTURE.REFUNDED` | ✅ audit row |
| anything else | recorded only |

## `POST /webhooks/paypal/{merchant_id}`

Public endpoint called by PayPal. No JWT; authenticity is proven by verifying the PayPal signature
headers through PayPal's `verify-webhook-signature` API using the merchant's webhook ID.

Processing order:

1. Parse JSON (`400` if invalid).
2. Verify the signature (`400` if invalid; no event row is written).
3. Insert `paypal_webhook_events.event_id` **before** dispatch. The unique `event_id` makes
   duplicate deliveries a no-op (`200 {"status":"ignored"}`).
4. Dispatch, then stamp `processed_at`.
5. On dispatch failure, the event row stays unprocessed and the API returns `502`, so PayPal
   retries.

Responses:

| Status | Body | Meaning |
|---|---|---|
| `200` | `{"status":"processed","event_type":"…","result":"processed"}` | Applied |
| `200` | `{"status":"ignored","reason":"duplicate"}` | Already processed |
| `400` | `{"detail":"Invalid PayPal webhook signature"}` | Rejected |
| `422` | `{"detail":"Webhook payload is missing id or event_type"}` | Malformed event |
| `404` | `{"detail":"Merchant not found"}` | Unknown merchant ID |
| `501` | `{"detail":"PayPal is not connected for this merchant"}` | Merchant has no stored credentials |
| `502` | `{"detail":"Webhook processing failed"}` | Transient failure; PayPal should retry |

### Money invariants

- `CHECKOUT.ORDER.APPROVED` captures the approved PayPal order server-side (PayPal's documented
  server-side capture trigger). The order stays `pending_payment` until the capture-completed
  webhook arrives; a retry that PayPal reports as `ORDER_ALREADY_CAPTURED` is treated as success.
- `PAYMENT.CAPTURE.COMPLETED` calls the order service's webhook-only `mark_paid` transition.
- The captured amount and currency must match the order total and currency; mismatches are
  audited and ignored (the order stays `pending_payment`).
- Amounts come from the order service, never from the webhook payload or the client.
- Every money action writes a `payment_actions` row (`action`, `trigger`, `amount`, `result`,
  `detail`).
- A paid order posts one system message into its conversation (deduplicated by `event_id`).

## Creating a payment link

The internal service is `app/payments/service.py::create_payment_link_for_order`. The future
`create_payment_link` agent tool calls it (with `trigger="agent"`); there is no public HTTP route
for creating links yet.

Rules:

- Order must be `confirmed` with a positive total (`409` / `422` otherwise).
- The backend creates a PayPal Orders v2 order with `intent=CAPTURE` and the server-owned total.
- On success the order moves to `pending_payment` with `paypal_order_id`, `approval_link`, and
  `expires_at` (merchant recovery timeout).
- The approval link is what the chat shows to the buyer.
- Return/cancel URLs default to `{FRONTEND_BASE_URL}/checkout/result?order_id=…`.

## Refunds

The PayPal adapter supports `refund(capture_id, amount, currency)` and refund webhooks are
audited. The owner-facing refund endpoint and over-cap approval flow are Phase 5 work; refunds do
not change the order status in v1 (the status enum has no `refunded` value).

## Currencies

Only PayPal-supported currencies are allowed ([`../contracts/enums.md`](../contracts/enums.md)). The
store currency is validated at settings/catalogue setup; orders inherit it at draft creation.

## Testing

- Adapter tests use `httpx.MockTransport` (no network) for OAuth, order creation, and signature
  verification.
- Webhook/API tests use a fake client and the real Supabase test database.
- Live verification checklist once credentials exist: connect → create a sandbox buyer payment →
  confirm webhook receipt → order becomes `paid`.
