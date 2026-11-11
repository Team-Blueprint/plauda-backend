# Plauda

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Plauda gives every business a **24/7 AI employee**: it chats with customers strictly from the business's approved information, recommends real in-stock products, builds structured orders in chat, sends a PayPal checkout link, confirms payment only from a cryptographically verified PayPal webhook, and logs the sale to the owner's dashboard.

- **Live Storefront & Merchant Dashboard (Frontend):** <https://plauda.vercel.app>
- **Live Backend API:** <https://plauda.fastapicloud.dev>
- **Live Health Check:** <https://plauda.fastapicloud.dev/healthz>
- **Interactive Swagger Docs:** <https://plauda.fastapicloud.dev/docs>
- **OSI License:** [MIT License](LICENSE)

---

## How We Used PayPal & AI

Plauda is architected around a strict financial safety boundary: **the AI agent proposes, the service layer enforces, and the PayPal webhook confirms.**

### 1. PayPal Developer Platform Integration (Sandbox — `api-m.sandbox.paypal.com`)
- **Merchant OAuth 2.0 Onboarding (`/v1/oauth2/token`):** Merchants connect their PayPal Sandbox Client ID, Secret, and Webhook ID via `POST /settings/paypal`. Credentials are validated live against PayPal OAuth 2.0 and encrypted at rest using **Fernet (`AES-128-CBC` + `HMAC-SHA256`)** (`app/payments/crypto.py`).
- **PayPal Orders v2 Checkout Creation (`POST /v2/checkout/orders`):** Once a customer confirms their order draft in chat, the AI agent invokes the controlled `create_payment_link` tool (`app/agent/tools/orders.py` → `app/payments/service.py`). This calls the PayPal Orders v2 API with a deterministic `PayPal-Request-Id` idempotency key and streams an interactive PayPal approval card (`approve` / `payer-action` link) directly into the customer's chat thread.
- **Retry-Safe Server-Side Capture (`POST /v2/checkout/orders/{id}/capture`):** When the buyer approves payment in PayPal Checkout and PayPal emits `CHECKOUT.ORDER.APPROVED`, the backend captures the payment server-side safely without double-charging on retries.
- **Cryptographic Webhook Verification (`/v1/notifications/verify-webhook-signature`):** The AI agent has **no tool** to mark an order as `paid` and never trusts a buyer's chat message claiming they paid. Orders transition to `paid` *only* when `POST /webhooks/paypal/{merchant_id}` (`app/payments/webhooks.py`) verifies the PayPal cryptographic signature, records the `event_id` in the idempotent `paypal_webhook_events` table, logs the capture to `payment_actions`, updates merchant revenue, and pushes a verified receipt card into the customer's chat stream.
- **Controlled Refunds (`/v2/payments/captures/{capture_id}/refund`):** Wired in `app/payments/paypal/client.py` with full audit logging.

### 2. AI Models, Agent Orchestration & Hybrid RAG
- **PydanticAI Agent Orchestration (`app/agent/agent.py`):** Orchestrates the conversational AI employee using tenant-scoped dependency injection (`AgentDeps`) so the model can only access the current merchant's data.
- **Groq LLM Inference (`openai/gpt-oss-120b`):** Powers low-latency, grounded customer conversations, product recommendations, and autonomous tool selection streamed token-by-token over Server-Sent Events (SSE).
- **Typed Agent Tools (`app/agent/tools/`):**
  - `lookup_catalogue`: Queries live PostgreSQL products, variants, prices, and stock counts.
  - `search_business_info`: Runs hybrid RAG retrieval over the merchant's `about`, `policies`, and `faq` markdown documents.
  - `start_order`, `add_order_item`, `remove_order_item`, `set_delivery_details`, `confirm_order`: Builds and validates structured order drafts with server-side price/total calculation and variant stock enforcement.
  - `create_payment_link`: Generates the PayPal Orders v2 checkout link for a confirmed order.
  - `request_human_handoff`: Immediately pauses the AI employee (`ai` → `handoff_requested`) and alerts human staff in the merchant inbox so AI and staff never talk over each other.
- **Hybrid RAG (`pgvector` + `pg_trgm`) & Multi-Provider Embeddings (`app/rag/`):** Merchant policies and FAQs are chunked by markdown headings and indexed in Supabase Postgres using both **HNSW vector indexes** and **GIN trigram/keyword indexes**. Supports **Google Gemini (`gemini-embedding-001`)**, **Cloudflare Workers AI (`@cf/baai/bge-m3`)**, and local **Ollama (`bge-m3`)** with atomic chunk replacement so upstream outages never wipe existing store knowledge.

---

## Sponsor Integration: Postman

We built a complete **Postman Collection v2.1** and environment suite in [`postman/`](postman/) generated from our OpenAPI contract (`docs/contracts/openapi.json`):

- **[`postman/Plauda_API.postman_collection.json`](postman/Plauda_API.postman_collection.json):** Contains all **49 API endpoints across 11 domain folders** (System Health, Merchant Auth, Catalogue & Variants, Delivery Zones, RAG Business Info, Store & PayPal Settings, Public Storefront & AI Chat, Merchant Handoff Inbox, Orders & PayPal Checkout Links, PayPal Webhooks, and Dashboard & Audit).
- **Automated `pm.test` Scripts & Variable Chaining:** Running `Login` or `Register` automatically asserts response status and saves `access_token` → `{{merchant_token}}`, `slug` → `{{store_slug}}`, and `id` → `{{merchant_id}}`. Running `Create Conversation` automatically chains `{{conversation_id}}` and `{{visitor_token}}` for immediate chat and handoff testing.
- **Pre-Configured Environments:** [`Plauda_Production.postman_environment.json`](postman/Plauda_Production.postman_environment.json) (`https://plauda.fastapicloud.dev`) and [`Plauda_Local.postman_environment.json`](postman/Plauda_Local.postman_environment.json) (`http://localhost:8000`). See [`postman/README.md`](postman/README.md) for import and Newman CLI instructions.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend API** | Python 3.12 · FastAPI · SQLAlchemy 2.0 (Async) · Alembic · Pydantic v2 · `uv` |
| **Database & Vector Search** | Supabase PostgreSQL · `pgvector` (HNSW) · `pg_trgm` (GIN) |
| **AI Agent & LLM** | PydanticAI · Groq (`openai/gpt-oss-120b`) |
| **Embeddings (RAG)** | Google Gemini (`gemini-embedding-001`) · Cloudflare Workers AI (`@cf/baai/bge-m3`) · Ollama (`bge-m3`) |
| **Payments** | PayPal Orders v2 REST API · PayPal Webhooks & Cryptographic Signature Verification |
| **Security** | JWT (`python-jose` + `bcrypt`) · SHA-256 Visitor Tokens · Fernet (`AES-128-CBC` + `HMAC-SHA256`) Credential Encryption |
| **Real-Time Streaming** | Server-Sent Events (SSE) in-process pub/sub hub |
| **API Testing & Contracts** | Postman Collection v2.1 · Newman · `pytest` (`129` automated tests) · `ruff` |
| **Frontend & Hosting** | Next.js / React on Vercel (`plauda.vercel.app`) · FastAPI Cloud (`plauda.fastapicloud.dev`) |

---

## Repo Layout

```text
plauda/
├── LICENSE                       ← OSI-approved MIT License
├── README.md                     ← Project overview, PayPal/AI architecture & setup guide
├── postman/                      ← Postman Collection v2.1 (49 requests) + Prod/Local environments
├── docs/                         ← Architecture, AI grounding rules, PayPal flows & API contracts
│   └── contracts/                ← openapi.json, sse.md, enums.md
└── backend/
    ├── app/                      ← FastAPI application (auth, merchants, rag, agent, orders, payments, inbox, dashboard)
    ├── alembic/                  ← Async database migrations (0001–0006)
    └── tests/                    ← 129 unit & integration tests
```

---

## Local Setup & Quickstart

Requires **Python 3.12+** and **[uv](https://docs.astral.sh/uv/)**.

### 1. Install Dependencies & Configure Environment

```bash
cd backend
uv sync
cp .env.example .env
```

Fill in `backend/.env`:
- `DATABASE_URL`: PostgreSQL / Supabase connection string (`postgresql+asyncpg://...`)
- `JWT_SECRET`: Secret key for signing merchant JWTs
- `CREDENTIAL_ENCRYPTION_KEY`: Fernet key for encrypting merchant PayPal credentials:
  ```bash
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `GROQ_API_KEY`: Groq API key for live `openai/gpt-oss-120b` agent turns
- `EMBEDDING_PROVIDER` + `GEMINI_API_KEY` (or Cloudflare / Ollama credentials) for RAG indexing

### 2. Enable `pgvector` & Run Database Migrations

In your Postgres / Supabase SQL editor (once per database):

```sql
create extension if not exists vector;
create extension if not exists pg_trgm;
```

Then apply migrations and start the development server:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

- **Local Swagger UI:** <http://localhost:8000/docs>
- **Local Health Check:** <http://localhost:8000/healthz>

### 3. Run the Automated Test Suite

```bash
uv run pytest -q
```

Offline unit tests run automatically; database-backed integration tests run when `TEST_DATABASE_URL` is configured (run serially with `uv run pytest -q`).

---

## Documentation Index

- [`docs/README.md`](docs/README.md) — Full documentation index
- [`docs/ai.md`](docs/ai.md) — AI agent architecture, hybrid RAG pipeline, and grounding guardrails
- [`docs/api/payments.md`](docs/api/payments.md) — PayPal Sandbox setup, Orders v2 flow, and webhook verification
- [`docs/api/orders.md`](docs/api/orders.md) — Order state machine and server-side total calculation
- [`docs/api/conversations.md`](docs/api/conversations.md) — Visitor threads, SSE streaming, and human handoff
- [`docs/api/dashboard.md`](docs/api/dashboard.md) — Revenue summary and payment audit ledger
- [`postman/README.md`](postman/README.md) — Postman Collection v2.1 & environment guide

---

## License

This project is open-source software licensed under the **[MIT License](LICENSE)**.
