# Build status

Last updated: 2026-11-02

## Phase 0 — Foundations (backend) — ✅ complete

| Task | Status |
|---|---|
| Monorepo scaffold: `backend/` with uv, FastAPI, ruff, pytest | ✅ |
| `config.py` (pydantic-settings) + `.env.example` with every key | ✅ |
| SQLAlchemy 2.0 async engine + Supabase pooler handling (SSL, statement cache) | ✅ |
| Alembic wired (async) + migration `0001` (merchants, users) | ✅ |
| JWT auth: `POST /auth/register`, `POST /auth/login`, `GET /auth/me` (bcrypt + jose) | ✅ |
| CORS, `/healthz`, JSON structured logging, error handlers | ✅ |
| Tests: security units, healthz, auth API | ✅ |
| CI: ruff + format check + pytest | ✅ |
| Contracts for frontend: `openapi.json`, `sse.md`, `enums.md`, API guides | ✅ |
| Migration `0001` applied to Supabase | ✅ |
| Live HTTP verification: `/healthz` (db ok), register → login → me | ✅ 2026-10-29 |

**Done when:** register/login works against Supabase; migrations apply cleanly from an empty DB;
health check green. — ✅ **All verified.**

> Dev note: this network intercepts TLS, so `backend/.env` uses `DATABASE_SSL_MODE=require`
> (encrypted, no certificate verification). The default stays `verify-full`; switch back on a
> normal network.

## Phase 1 — Catalogue & RAG — 🔨 backend part done, AI paused

| Task | Status |
|---|---|
| Products + variants CRUD (tenant-scoped, PayPal currency rules, max 5 images) | ✅ |
| Delivery zones CRUD | ✅ |
| Business info markdown storage (`about` / `policies` / `faq`) | ✅ storage only |
| Store settings (currency, refund cap, recovery toggle/timeout) | ✅ |
| Public store meta `GET /public/chat/{slug}/meta` (no auth) | ✅ |
| Product image upload → Supabase Storage (`POST/DELETE /products/{id}/images`) | ✅ live-verified |
| Migration `0002` (products, variants, zones, business info, pg_trgm) | ✅ |
| Tests: catalogue, variants, zones, business info, settings, public meta, storage | ✅ |
| **AI: chunker, embedders (CF/Ollama/Gemini), hybrid retrieval** | ⏸ paused by request |
| Procrastinate worker setup | ⏸ deferred until worker tasks (AI) begin |

## Phase 2 — Grounded chat / conversations — 🔨 conversation foundation done, AI paused

| Task | Status |
|---|---|
| Migration `0004`: `customers`, `conversations`, `messages`, order FKs | ✅ applied |
| Visitor thread creation (`POST /public/chat/{slug}/conversations`) | ✅ |
| Visitor token: returned raw once, SHA-256 hash stored, bearer auth | ✅ |
| Public history + visitor message + handoff button endpoints | ✅ |
| Owner inbox: list/detail/history/accept/reply/return-to-ai/close | ✅ |
| Conversation status machine (`ai → handoff_requested → human_active → closed`, `human_active → ai`) | ✅ |
| In-process SSE hub + visitor/inbox streams (`message`, `conversation_update`) | ✅ |
| Tests: token isolation, handoff lifecycle, tenant scoping, pagination, order link, SSE hub | ✅ 9 pass |
| **AI turns, handoff classifier, streaming turn events** | ⏸ paused by request |

## Phase 3 — Ordering & handoff — 🔨 order backend done, AI paused

| Task | Status |
|---|---|
| Order draft model + state machine (`draft → confirmed`, totals recomputed server-side) | ✅ |
| Orders API: `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel`, `POST /orders/{id}/fulfill` | ✅ |
| `paid` webhook-only invariant + `pending_payment`/`paid`/`fulfill`/`expire` service paths | ✅ |
| Product delete guard for order history (`409`) | ✅ |
| Migration `0003` (orders, order_items, status check, recovery index) | ✅ applied |
| Tests: state machine, totals recomputation, merge, lifecycle, tenant scoping | ✅ 10 pass |
| **PydanticAI agent + tool registry + state-gated tools** | ⏸ paused by request |
| **Order tools wired into chat (`create_payment_link`, etc.)** | ⏸ paused by request |

## Phase 4 — PayPal — ✅ complete

| Task | Status |
|---|---|
| Migration `0005`: `paypal_webhook_events`, `payment_actions`, `merchants.paypal_webhook_id_enc` | ✅ applied |
| Fernet credential encryption (`CREDENTIAL_ENCRYPTION_KEY`) | ✅ |
| `GET/POST/DELETE /settings/paypal` + OAuth credential health check | ✅ |
| Orders v2 adapter: create/get/capture/refund (httpx, no SDK) | ✅ mock-tested |
| Webhook endpoint: signature verification + `event_id` idempotency + audit ledger | ✅ mock-tested |
| `CHECKOUT.ORDER.APPROVED` → server-side capture (retry-safe) | ✅ mock-tested |
| `PAYMENT.CAPTURE.COMPLETED` → `paid` + audit + chat receipt | ✅ mock-tested |
| Declined capture handling (buyer notice) + refund webhook audit | ✅ declined mock-tested |
| Internal `create_payment_link_for_order` service | ✅ mock-tested |
| Owner `POST /orders/{id}/payment-link` (idempotent, tenant-scoped) | ✅ 3 tests |
| Tests: crypto, adapter, settings, webhook idempotency/rejection, declined notice, link creation | ✅ 20 pass |
| **Live sandbox payment + webhook verification** | ✅ paid 2026-11-02; capture `1EA58572KJ470073T` completed for USD 10.00; webhook signatures verified |
| **Owner refund endpoint + over-cap approval** | ⏸ Phase 5 |

## Phase 5 — Recovery & operations — 🔨 dashboard + audit done, recovery paused

| Task | Status |
|---|---|
| Orders list/detail + conversation history APIs | ✅ earlier phases |
| `GET /dashboard/summary`: today's revenue, orders, live chats | ✅ 2 tests |
| `GET /audit`: filtered, paginated payment audit trail | ✅ 2 tests |
| Owner refund endpoint + over-cap approval | ⏸ next |
| Recovery worker + reminder/expiry jobs | ⏸ paused by request |
| Reminder tests: exactly one reminder then expiry; toggle off = silence | ⏸ paused |

## Phase 6 — Failover & hardening — ⏸ not started

## Test suite

Full backend suite: **74 tests** (offline units + Supabase-backed API tests). Runtime ~22–30 min
because every DB test round-trips to Supabase.

## Open items

| Item | Owner | Notes |
|---|---|---|
| PayPal sandbox credentials | ✅ connected | New sandbox app + webhook stored for `plauda-store`; rotate the secret after testing |
| PayPal sandbox buyer account | ✅ ready | Sandbox personal/buyer login available for the checkout test |
| Public HTTPS URL for webhooks | ✅ ngrok verified | `APP_BASE_URL/webhooks/paypal/{merchant_id}`; update PayPal if the tunnel URL changes |
| Frontend repo/location | Frontend dev | Contracts in `docs/contracts/` are ready |
| Domain for `plauda.app` links | You | Open question in BUILD_PLAN §16 |
| AI start approval | You | Paused until you say go |
| Recovery worker | You | Paused by request; dashboard + audit are done |
| Rotate Supabase DB password | You (optional) | The dev connection string was shared in chat; it is only in gitignored `.env` |
