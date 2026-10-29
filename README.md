# Plauda

Plauda gives every business an **AI employee**: it chats with customers from the business's
approved information, recommends products, builds structured orders, sends a PayPal checkout,
confirms payment from a verified webhook, and logs the sale to the owner's dashboard — 24/7.

> Status: **Phase 0 — Foundations** (backend). See `BUILD_PLAN.md` for the full plan and
> `TASK_DIVISION.md` for the track split.

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI · SQLAlchemy 2.0 async · Alembic · Pydantic v2 · uv |
| DB | Supabase Postgres + pgvector |
| Agent | PydanticAI (Groq `llama-3.3-70b-versatile`) |
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
# → fill DATABASE_URL (Supabase pooler string) and JWT_SECRET
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
- [`docs/contracts/openapi.json`](docs/contracts/openapi.json) — generated REST surface
- [`docs/contracts/sse.md`](docs/contracts/sse.md) — chat streaming events
- [`docs/contracts/enums.md`](docs/contracts/enums.md) — status/role enums
- [`docs/architecture.md`](docs/architecture.md) — backend internals
- [`docs/status.md`](docs/status.md) — what's built / what's next
