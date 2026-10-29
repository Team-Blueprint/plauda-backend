# Build status

Last updated: 2026-10-29

## Phase 0 — Foundations (backend) — ✅ complete

| Task | Status |
|---|---|
| Monorepo scaffold: `backend/` with uv, FastAPI, ruff, pytest | ✅ |
| `config.py` (pydantic-settings) + `.env.example` with every key | ✅ |
| SQLAlchemy 2.0 async engine + Supabase pooler handling (SSL, statement cache) | ✅ |
| Alembic wired (async) + migration `0001` (merchants, users) | ✅ |
| JWT auth: `POST /auth/register`, `POST /auth/login`, `GET /auth/me` (bcrypt + jose) | ✅ |
| CORS, `/healthz`, JSON structured logging, error handlers | ✅ |
| Tests: security units, healthz, auth API | ✅ 9 pass (against real Supabase) |
| CI: ruff + format check + pytest | ✅ |
| Contracts for frontend: `openapi.json`, `sse.md`, `enums.md`, API guides | ✅ |
| Migration `0001` applied to Supabase | ✅ |
| Live HTTP verification: `/healthz` (db ok), register → login → me | ✅ 2026-10-29 |

**Done when:** register/login works against Supabase; migrations apply cleanly from an empty DB;
health check green. — ✅ **All verified.**

> Dev note: this network intercepts TLS, so `backend/.env` uses `DATABASE_SSL_MODE=require`
> (encrypted, no certificate verification). The default stays `verify-full`; switch back on a
> normal network.

## Phase 1 — Catalogue & RAG — ⏸ not started

Backend parts (products/variants/zones CRUD, settings, slug + public meta) and AI parts (chunker,
embeddings, hybrid retrieval) are planned. **AI work is paused by request** — will confirm before
starting any AI/embedding/agent work.

## Phase 2 — Grounded chat — ⏸ not started

## Phase 3 — Ordering & handoff — ⏸ not started

## Phase 4 — PayPal — ⏸ not started

## Phase 5 — Recovery & operations — ⏸ not started

## Phase 6 — Failover & hardening — ⏸ not started

## Open items

| Item | Owner | Notes |
|---|---|---|
| Frontend repo/location | Frontend dev | Contracts in `docs/contracts/` are ready |
| Domain for `plauda.app` links | You | Open question in BUILD_PLAN §16 |
| AI start approval | You | Paused until you say go |
| Rotate Supabase DB password | You (optional) | The dev connection string was shared in chat; it is only in gitignored `.env` |
