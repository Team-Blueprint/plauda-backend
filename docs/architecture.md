# Backend architecture

> Phases 0–1, the non-AI parts of Phase 3 (orders foundation + owner payment-link endpoint), the
> conversations/SSE foundation (including visitor messages), the PayPal backend layer, and the
> Phase 5 dashboard summary + payment audit endpoints are implemented. AI/agent/RAG work and the
> recovery worker are paused — see `status.md`.

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Runtime | Python 3.12+ | uv-managed virtualenv |
| API | FastAPI | Pydantic v2 schemas, async endpoints |
| ORM | SQLAlchemy 2.0 async (`asyncpg`) | typed `Mapped[...]` models |
| Migrations | Alembic (async template) | migrations are the schema truth |
| DB | Supabase Postgres (+ pgvector from Phase 1) | connect through the Supavisor pooler |
| Auth | JWT (HS256, python-jose) + bcrypt | Bearer tokens, no cookies |
| Lint/format | ruff | line length 100, target py312 |
| Tests | pytest + pytest-asyncio | DB tests gated on `TEST_DATABASE_URL` |

## Module layout

```
backend/
├── app/
│   ├── main.py            FastAPI app factory, CORS, /healthz
│   ├── config.py          pydantic-settings; all env vars in one place
│   ├── deps.py            shared FastAPI dependencies (current user)
│   ├── errors.py          exception handlers (IntegrityError → 409, catch-all → 500)
│   ├── logging.py         JSON structured logging
│   ├── db/
│   │   ├── base.py        DeclarativeBase
│   │   ├── engine.py      engine factory + Supabase URL normalization (SSL, pooler)
│   │   ├── session.py     async session factory + get_session dependency
│   │   └── models.py      SQLAlchemy models (merchants, users, catalogue, orders, chat, payments)
│   ├── auth/
│       ├── routes.py      /auth/register, /auth/login, /auth/me
│       ├── schemas.py     request/response models
│       └── security.py    bcrypt hashing + JWT encode/decode
│   ├── merchants/
│       ├── catalogue.py   products + variants CRUD + image upload
│       ├── zones.py       delivery zones CRUD
│       ├── business_info.py  markdown docs (about/policies/faq)
│       ├── settings.py    store settings + chat link
│       ├── public.py      public store meta (no auth)
│       ├── storage.py     Supabase Storage adapter (bucket/upload/delete)
│       ├── schemas.py     Phase 1 request/response models
│       └── constants.py   PayPal currencies, image rules, info sources
│   ├── orders/
│       ├── routes.py      dashboard orders list/detail/payment-link/cancel/fulfill
│       ├── service.py     order creation, item/delivery mutations, totals recomputation
│       ├── state_machine.py  statuses + allowed transitions (paid = webhook only)
│       ├── schemas.py     order response models
│       └── errors.py      domain errors mapped to HTTP by app/errors.py
│   ├── conversations/
│       ├── routes_public.py   visitor thread create/history/message/handoff/stream
│       ├── routes_inbox.py    owner inbox list/detail/reply/accept/return/close/stream
│       ├── service.py         thread lifecycle, messages, status transitions
│       ├── state_machine.py   ai → handoff_requested → human_active → closed
│       ├── sse.py             in-process pub/sub hub + SSE frame helpers
│       ├── tokens.py          visitor token generation + SHA-256 hashing
│       ├── deps.py            visitor bearer-token dependency
│       ├── schemas.py         conversation/message models
│       └── errors.py          domain errors mapped to HTTP by app/errors.py
│   ├── dashboard/
│       ├── routes.py          /dashboard/summary + /audit
│       ├── service.py         aggregate revenue/order/chat queries + audit pagination
│       └── schemas.py         summary/audit response models
│   └── payments/
│       ├── routes.py          /settings/paypal + /webhooks/paypal
│       ├── service.py         create_payment_link_for_order (agent tool later)
│       ├── webhooks.py        signature check, event-id idempotency, dispatch
│       ├── crypto.py          Fernet encrypt/decrypt for merchant credentials
│       ├── audit.py           payment_actions writer
│       ├── schemas.py         PayPal setup/status models
│       ├── errors.py          domain errors mapped to HTTP by app/errors.py
│       └── paypal/client.py   Orders v2 + webhook verification adapter (httpx)
├── alembic/               async migrations
├── scripts/export_openapi.py
└── tests/
```

Later phases add sibling packages: `rag/`, `agent/`, `workers/` — exactly as laid out in
`BUILD_PLAN.md` §10.

## Request lifecycle

```
HTTP → FastAPI router
     → dependencies (get_session / get_current_user)
     → endpoint (async)
     → SQLAlchemy async session → Supabase Postgres
     → Pydantic response model
     → JSON
```

`get_current_user` decodes the JWT, loads the `users` row (with its `merchants` row), and every
endpoint receives a fully-typed `User`. Errors are raised as `HTTPException` and rendered as
`{"detail": ...}`.

## Multi-tenancy rule (non-negotiable)

- `merchants` is the tenant. Every future table carries `merchant_id`.
- **Every query must filter by `merchant_id`.** The JWT also carries a `merchant_id` claim so a
  missing filter is caught in review.
- The public chat resolves tenant by `slug`; authenticated APIs resolve it from the token.

## Data model — Phase 0

### `merchants`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | generated by the app |
| `name` | varchar(200) | store display name |
| `slug` | varchar(120) unique | public chat link key |
| `currency` | varchar(3) | default `USD`; PayPal allowlist enforced in Phase 1 |
| `settings` | jsonb | free-form merchant settings (default `{}`) |
| `paypal_client_id_enc` / `paypal_secret_enc` / `paypal_webhook_id_enc` | text | encrypted creds (Phase 4) |
| `paypal_env` | varchar(16) | `sandbox` / `live` (Phase 4) |
| `recovery_reminder_enabled` | boolean | default true (Phase 5) |
| `recovery_timeout_minutes` | int | default 120 (Phase 5) |
| `refund_cap` | numeric(12,2) | default 0 (Phase 4/5) |
| `created_at` / `updated_at` | timestamptz | server defaults |

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant_id` | UUID FK → merchants, cascade delete | indexed |
| `email` | varchar(320) unique | stored lowercase |
| `hashed_password` | text | bcrypt |
| `role` | varchar(16) | `owner` only in v1; `staff` reserved |
| `created_at` / `updated_at` | timestamptz | |

### `products`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant_id` | UUID FK → merchants, cascade delete | |
| `name` | varchar(200) | GIN trigram index (`pg_trgm`) for search |
| `description` | text | default `""` |
| `price` | numeric(12,2) | must be > 0 (API rule) |
| `currency` | varchar(3) | must equal the store currency; PayPal allowlist |
| `active` | boolean | default true; inactive products are hidden from the AI/chat |
| `image_urls` | text[] | max 5 (API rule) |
| `created_at` / `updated_at` | timestamptz | |

Indexes: `(merchant_id, active)`, GIN trigram on `name`.

### `product_variants`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `product_id` | UUID FK → products, cascade delete | indexed |
| `name` | varchar(120) | e.g. "Red" |
| `options` | jsonb | e.g. `{"color": "red"}` |
| `price_override` | numeric(12,2) null | null = use product price |
| `stock` | int | default 0 |

### `delivery_zones`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant_id` | UUID FK → merchants, cascade delete | indexed |
| `name` | varchar(120) | |
| `areas` | jsonb (list) | area names covered |
| `fee` | numeric(12,2) | default 0 |
| `eta_days` | int | default 0 |

### `business_info_documents`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant_id` | UUID FK → merchants, cascade delete | indexed |
| `source` | varchar(16) | `about` / `policies` / `faq` (check constraint) |
| `content` | text | markdown; unique per `(merchant_id, source)` |
| `created_at` / `updated_at` | timestamptz | |

Raw markdown lives here; Phase 1 AI chunks it into `knowledge_chunks` (not built yet).

### `orders`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant_id` | UUID FK → merchants, cascade delete | composite index `(merchant_id, status)` |
| `conversation_id` / `customer_id` | UUID null | FK → conversations/customers, set null on delete |
| `status` | varchar(20) | check constraint, see state machine below |
| `currency` | varchar(3) | copied from the merchant at draft creation |
| `subtotal` / `delivery_fee` / `total` | numeric(12,2) null | written only by the order service |
| `delivery_details` | jsonb null | `{zone_id, zone_name, fee, eta_days, address}` |
| `paypal_order_id` / `approval_link` | text null | Phase 4 |
| `reminder_count` | int | default 0 (Phase 5) |
| `paid_at` / `expires_at` | timestamptz null | |
| `created_at` / `updated_at` | timestamptz | |

Partial index `(merchant_id) WHERE status = 'pending_payment'` for the recovery sweep.

### `order_items`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `order_id` | UUID FK → orders, cascade delete | indexed |
| `product_id` | UUID FK → products, set null on delete | nullable; snapshot preserves history |
| `variant_id` | UUID FK → product_variants, set null on delete | nullable |
| `name_snapshot` | varchar(200) | product name at add/confirm time |
| `variant_snapshot` | jsonb null | `{name, options}` |
| `qty` | int | merged when the same product+variant is added twice |
| `unit_price` | numeric(12,2) | refreshed from the catalogue at confirmation |

The dashboard cannot delete a product with order history (`409`) — deactivate it instead.

### `customers`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant_id` | UUID FK → merchants, cascade delete | indexed |
| `name` / `contact` | varchar(200) / varchar(320) null | optional visitor-provided identity |
| `notes` | text | default `""` (owner notes, reserved) |
| `created_at` / `updated_at` | timestamptz | |

No accounts or login in v1 — a customer row is created with each new thread.

### `conversations`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant_id` | UUID FK → merchants, cascade delete | index `(merchant_id, status)` |
| `customer_id` | UUID FK → customers, set null on delete | |
| `channel` | varchar(16) | `web` only (check constraint) |
| `status` | varchar(20) | `ai` / `handoff_requested` / `human_active` / `closed` |
| `visitor_token_hash` | varchar(64) unique | SHA-256 of the raw visitor token; raw token is returned once |
| `handoff_reason` | varchar(500) null | visitor's optional note |
| `summary` | text null | reserved for the AI summary |
| `started_at` / `last_message_at` | timestamptz | |
| `created_at` / `updated_at` | timestamptz | |

### `messages`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `conversation_id` | UUID FK → conversations, cascade delete | index `(conversation_id, created_at)` |
| `role` | varchar(16) | `customer` / `agent` / `staff` / `system` / `tool` |
| `content` | text | |
| `meta` | jsonb | `{"kind": "handoff"\|"payment", "event_id": "…"}` etc. |
| `created_at` | timestamptz | |

### `paypal_webhook_events`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `event_id` | varchar(128) unique | PayPal event ID — idempotency key |
| `merchant_id` | UUID FK → merchants, cascade delete | indexed |
| `event_type` | varchar(80) | e.g. `PAYMENT.CAPTURE.COMPLETED` |
| `resource_id` | varchar(128) null | capture/order/refund ID |
| `payload` | jsonb | full webhook body |
| `signature_verified` | boolean | true once accepted |
| `processed_at` | timestamptz null | null = retryable failure |
| `created_at` | timestamptz | |

### `payment_actions`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant_id` | UUID FK → merchants, cascade delete | indexed |
| `order_id` | UUID FK → orders, cascade delete | index `(order_id, created_at)` |
| `action` | varchar(16) | `create_link` / `refund` / `mark_paid` / `receipt` / `expire` |
| `trigger` | varchar(16) | `agent` / `webhook` / `staff` / `system` |
| `amount` | numeric(12,2) null | money moved/requested |
| `result` | varchar(32) | `success` / `declined` / `ignored` / `failed` |
| `detail` | jsonb | PayPal IDs, capture IDs, event IDs |
| `created_at` | timestamptz | |

## Orders & the money invariant

- `app/orders/service.py` is the only writer of totals and status transitions.
- At confirmation: `subtotal = Σ(qty × current unit_price)`, `delivery_fee = current zone fee`,
  `total = subtotal + delivery_fee` — all quantized to 2 decimal places.
- Catalogue/zone rows are re-read at confirmation, so stale chat data can never set a price.
- `paid` is written by the verified PayPal webhook only (`ensure_transition` rejects every other
  trigger). Owner API exposes only `cancel` and `fulfill`.
- `fulfilled` requires `paid`; `cancelled` requires pre-payment; terminal states never transition.

## Conversations & SSE

- A visitor gets a raw token **once** at thread creation; the DB stores only its SHA-256 hash.
  Public endpoints require `Authorization: Bearer <visitor_token>`.
- Missing token → `401`; wrong token/unknown thread → `404` (same response — no enumeration).
- Owner endpoints are tenant-scoped and enforce the status machine. Staff replies are only allowed
  while `human_active`; handoff is visitor-triggered; accept/return/close are owner-only.
- `app/conversations/sse.py` is an in-process asyncio pub/sub hub with two channel kinds:
  `("conversation", id)` for the visitor and `("merchant", merchant_id)` for the inbox. Single API
  process only; if the API is scaled out, swap the transport for Postgres `LISTEN/NOTIFY` without
  changing the event contract.
- Streams are `GET /public/conversations/{id}/stream` and `GET /conversations/stream`. The frontend
  must use streaming `fetch()` because `EventSource` cannot send an `Authorization` header.
- Events: `message` (persisted message) and `conversation_update` (status/customer summary), plus
  keepalive comments. See `docs/contracts/sse.md`.
- SSE endpoints authenticate with a short-lived DB session and do not hold a connection for the
  lifetime of the stream.

## Dashboard & audit

- `GET /dashboard/summary` uses one conditional-aggregate query for orders and one for
  conversations. The day window is UTC midnight to midnight; paid revenue is based on `paid_at`,
  while `orders_today` is based on `created_at`.
- `GET /audit` reads `payment_actions` joined to the owning order for currency/status context.
  It is tenant-scoped, newest-first, filterable by order/action/trigger/result/time, and paginated.
- Audit rows are append-only. The endpoint never mutates money state; refund and recovery work
  will add rows through the same `record_action` helper.

## PayPal payments

- Merchant credentials (client ID, secret, webhook ID, env) are encrypted with Fernet using
  `CREDENTIAL_ENCRYPTION_KEY`; the API never returns them.
- `POST /settings/paypal` verifies the credentials with PayPal OAuth before saving.
- Webhook URL: `{APP_BASE_URL}/webhooks/paypal/{merchant_id}`. Authenticity is checked with PayPal's
  `verify-webhook-signature` API using the merchant's webhook ID (client credentials alone are not
  enough).
- `paypal_webhook_events.event_id` is the idempotency key: the row is committed **before** dispatch,
  duplicates are acknowledged as ignored, and failed dispatches leave `processed_at` null so PayPal
  can retry.
- `PAYMENT.CAPTURE.COMPLETED` is the only path that marks an order `paid`; it calls the order
  service's webhook-only transition and writes a `payment_actions` audit row. A receipt system
  message is posted once per event into the linked conversation. Captured amount/currency must
  match the order; mismatches are audited and ignored.
- `CHECKOUT.ORDER.APPROVED` captures the approved order server-side (PayPal's documented
  server-side trigger); the order stays `pending_payment` until `capture.completed` arrives.
- `create_payment_link_for_order` is the internal service the future `create_payment_link` agent
  tool calls. It requires a `confirmed` order, creates a PayPal Orders v2 order with
  `intent=CAPTURE`, and moves the order to `pending_payment` with the approval link and expiry.
- Refund adapter + refund-webhook audit exist; the owner-facing refund endpoint and over-cap
  approval are Phase 5.

## Supabase specifics

- Paste the **connection-pooling** string from the Supabase dashboard as `DATABASE_URL` — plain
  `postgresql://` is fine. The app converts it to `postgresql+asyncpg://`.
- `app/db/engine.py` strips `sslmode` (asyncpg doesn't understand it), enables SSL for Supabase
  hosts, and disables statement caching when the host is a Supavisor pooler (transaction mode).
- Run `create extension if not exists vector;` once in the Supabase SQL editor (needed from
  Phase 1 AI). Migration `0002` also enables `pg_trgm` for product-name search.
- Alembic is the only way schema changes happen — no dashboard edits.

## Product image storage

- Adapter: `app/merchants/storage.py` — thin httpx client to the Storage REST API (no SDK).
- Bucket: `SUPABASE_STORAGE_BUCKET` (default `product-images`), **public**, auto-created on first
  upload.
- Object path: `{merchant_id}/{product_id}/{uuid}{ext}`; public URL is
  `{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}`.
- Auth: `SUPABASE_SERVICE_KEY` (legacy `service_role` JWT or `sb_secret_...`). The adapter sends
  the key on both `apikey` and `Authorization: Bearer` because `sb_secret_` keys are not JWTs and
  Storage requires an Authorization header. The key never reaches the frontend — uploads are
  proxied through the authenticated API.
- Limits enforced by the API: image content-types only, 5 MB/file, 5 images/product.

## Configuration

All settings live in `app/config.py` and are loaded from environment / `backend/.env`
(template: `backend/.env.example`). Notable keys: `DATABASE_URL`, `JWT_SECRET`,
`JWT_EXPIRY_MINUTES`, `CORS_ORIGINS` (JSON list), `LOG_LEVEL`, `CREDENTIAL_ENCRYPTION_KEY`
(required to store PayPal credentials — losing it makes stored credentials undecryptable), and
Phase 1+ placeholders (`EMBEDDING_PROVIDER`, `GROQ_API_KEY`, global PayPal keys).

## Logging & errors

- JSON-per-line logging to stdout (`app/logging.py`), level via `LOG_LEVEL`.
- `IntegrityError` → `409 {"detail": "Resource already exists"}`.
- Order domain errors (`app/orders/errors.py`), conversation errors
  (`app/conversations/errors.py`), and payment errors (`app/payments/errors.py`) map to `400` /
  `404` / `409` / `422` / `501` / `502` with their message.
- Unhandled exceptions → logged with traceback, client sees `500 {"detail": "Internal server error"}`.

## Testing

- `uv run pytest -q` — unit tests (security, healthz, SSE hub, crypto, PayPal adapter with
  `httpx.MockTransport`) run offline.
- DB-backed tests (`tests/test_auth_api.py`, `test_catalogue_api.py`, `test_orders.py`,
  `test_conversations_api.py`, `test_payments.py`) run only when `TEST_DATABASE_URL` is set; they
  create the schema with `metadata.create_all` and clean up rows marked `@plauda-test.com` /
  slug prefix `pytest-`.
- The suite round-trips to Supabase and takes ~30 minutes.
- CI (`.github/workflows/ci.yml`): `ruff check`, `ruff format --check`, `pytest`.

## Conventions

- Async everywhere; no sync DB calls.
- One Pydantic schema module per feature (`schemas.py`), one router module per feature.
- Money: `Numeric(12,2)` / `Decimal`; never floats.
- UUID primary keys; UTC timestamps (`timestamptz`).
- New env vars must be added to `config.py` **and** `.env.example`.
- Contracts (`docs/contracts/openapi.json`) regenerated with `make openapi` at the end of a phase.
