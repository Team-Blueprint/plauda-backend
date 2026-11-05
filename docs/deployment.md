# Deployment

Plauda runs on **FastAPI Cloud** with Supabase Postgres. There is no Docker image; FastAPI Cloud
builds the Python project directly with `uv`.

## Current deployment

| Item | Value |
|---|---|
| App | `plauda` |
| Team | `abasiofon135-14996b21` |
| App ID | `bca5d761-5238-4256-a0ac-151160935bb3` |
| API | <https://plauda.fastapicloud.dev> |
| Health check | <https://plauda.fastapicloud.dev/healthz> |
| API docs | <https://plauda.fastapicloud.dev/docs> |
| Frontend | <https://plauda.vercel.app> |

The deployable project is the `backend/` directory. Its `pyproject.toml` declares the ASGI
entrypoint:

```toml
[tool.fastapi]
entrypoint = "app.main:app"
```

`.fastapicloudignore` keeps `.env`, tests, scripts, and caches out of the uploaded bundle.

## First-time setup

```bash
cd backend
uv run fastapi cloud login
uv run fastapi cloud apps create --name plauda --link --path .
```

If the app already exists, link the directory instead of creating it:

```bash
cd backend
uv run fastapi cloud apps link --app-id bca5d761-5238-4256-a0ac-151160935bb3 --path .
```

## Environment variables

`backend/.env` is gitignored, so it is **not** uploaded. Production values live in FastAPI Cloud:

```bash
cd backend
uv run fastapi cloud env set NAME 'value' --no-redeploy
# add --secret for credentials
```

| Variable | Production value |
|---|---|
| `ENV` | `prod` |
| `APP_BASE_URL` | `https://plauda.fastapicloud.dev` |
| `FRONTEND_BASE_URL` | `https://plauda.vercel.app` |
| `CORS_ORIGINS` | `["*"]` (or the explicit frontend origin) |
| `DATABASE_URL` | Supabase pooler URL |
| `DATABASE_SSL_MODE` | `verify-full` |
| `JWT_SECRET` | secret |
| `CREDENTIAL_ENCRYPTION_KEY` | secret (Fernet key) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | image storage |
| `GROQ_API_KEY`, `GROQ_AGENT_MODEL`, `GROQ_CHEAP_MODEL` | agent |
| `EMBEDDING_PROVIDER` | `gemini` |
| `GEMINI_API_KEY` | embeddings |
| `CF_ACCOUNT_ID`, `CF_API_TOKEN` | embeddings backup |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_ENV` | payments |

`TEST_DATABASE_URL` is intentionally not set in production; tests are excluded from the bundle.

## Deploy

```bash
cd backend
uv run fastapi deploy
```

Verify:

```bash
curl https://plauda.fastapicloud.dev/healthz
# {"status":"ok","app":"plauda","env":"prod","db":"ok"}
```

Recent logs:

```bash
uv run fastapi cloud logs --no-follow --tail 50 --since 30m
```

## PayPal webhook

Register this URL in the merchant's PayPal REST app (Webhooks section):

```
https://plauda.fastapicloud.dev/webhooks/paypal/{merchant_id}
```

For the current sandbox store `plauda-store`
(`merchant_id = 1db0327a-b40f-4054-b63e-70290c0cae55`):

```
https://plauda.fastapicloud.dev/webhooks/paypal/1db0327a-b40f-4054-b63e-70290c0cae55
```

This URL was applied to the live sandbox webhook on 2026-11-05 (webhook ID
`7WK76955E3394400T`, 5 subscribed events) with a PayPal `PATCH`, so the stored webhook ID remains
valid and the old ngrok URL is retired. `FRONTEND_BASE_URL` builds the PayPal return/cancel
`/checkout/result` URLs and the public `chat_link`. `APP_BASE_URL` is set to the deployed API
origin for webhook URLs and future absolute links (runtime checkout URLs currently derive from
`FRONTEND_BASE_URL`).

## CI/CD (optional)

```bash
cd backend
uv run fastapi cloud setup-ci
```

This adds a GitHub Actions workflow that deploys on push. Without it, deploy manually with
`uv run fastapi deploy`.
