# Plauda

Plauda gives every business an **AI employee**: it chats with customers from the business's
approved information, recommends products, builds structured orders, sends a PayPal checkout,
confirms payment from a verified webhook, and logs the sale to the owner's dashboard — 24/7.

> Status: **Phase 5 backend + AI agent core** — catalogue, orders, conversations/SSE, PayPal,
> dashboard summary, payment audit, RAG retrieval, and streamed grounded chat turns are built. The
> next AI slice is ordering tools; refunds and the recovery worker are paused. See `BUILD_PLAN.md`
> for the full plan and `TASK_DIVISION.md` for the track split.

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI · SQLAlchemy 2.0 async · Alembic · Pydantic v2 · uv |
| DB | Supabase Postgres + pgvector |
| Agent | PydanticAI (Groq `openai/gpt-oss-120b`) |
| Embeddings | `bge-m3` — Cloudflare Workers AI (prod), Ollama (local dev), Gemini (backup) |
| Jobs | Procrastinate (Postgres-backed) |
| Payments | PayPal Orders v2 + webhooks |

## Repo layout

```
plauda/
├── BUILD_PLAN.md                 ← build plan
├── TASK_DIVISION.md              ← team split
├── docs/contracts/               ← API + SSE + enums contracts (for the frontend dev)
└── backend/
    ├── app/                      ← FastAPI app
    ├── alembic/                  ← migrations
    └── tests/
```

## Backend quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
cp .env.example .env
# → fill DATABASE_URL (Supabase pooler string), JWT_SECRET, and CREDENTIAL_ENCRYPTION_KEY
#   (generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
#   Live chat turns also need GROQ_API_KEY; RAG needs Cloudflare Workers AI keys or a working Ollama
```

In the Supabase SQL editor, once per project:

```sql
create extension if not exists vector;
```

Then:

```bash
uv run alembic upgrade head   # or: make migrate
uv run uvicorn app.main:app --reload --port 8000   # or: make dev
```

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/healthz

### Tests

```bash
uv run pytest -q
```

DB-backed tests run only when `TEST_DATABASE_URL` is set; everything else runs offline.

## Documentation

- [`docs/README.md`](docs/README.md) — documentation index (start here)
- [`docs/api/auth.md`](docs/api/auth.md) — auth endpoint reference for the frontend
- [`docs/api/conventions.md`](docs/api/conventions.md) — auth header, errors, money, IDs, CORS
- [`docs/api/orders.md`](docs/api/orders.md) — dashboard orders
- [`docs/api/conversations.md`](docs/api/conversations.md) — visitor threads, handoff, inbox
- [`docs/api/payments.md`](docs/api/payments.md) — PayPal setup, webhooks, payment links
- [`docs/api/dashboard.md`](docs/api/dashboard.md) — revenue summary and payment audit
- [`docs/contracts/openapi.json`](docs/contracts/openapi.json) — generated REST surface
- [`docs/contracts/sse.md`](docs/contracts/sse.md) — chat + inbox streaming events
- [`docs/contracts/enums.md`](docs/contracts/enums.md) — status/role enums
- [`docs/ai.md`](docs/ai.md) — AI architecture, RAG/agent plan, grounding rules
- [`docs/architecture.md`](docs/architecture.md) — backend internals
- [`docs/status.md`](docs/status.md) — what's built / what's next
