# Auth API — Phase 0

Every merchant is a **store** with exactly **one owner account** in v1. Registering creates both
in one transaction. Staff accounts are backlog (see `contracts/enums.md`).

## `POST /auth/register`

Creates the merchant (store) + owner account and returns a ready-to-use access token.

**Request**

```json
{
  "store_name": "Ada's Closet",
  "email": "ada@example.com",
  "password": "s3cret-pass"
}
```

| Field | Rules |
|---|---|
| `store_name` | 2–200 chars; used to derive the public slug (`ada-s-closet`) |
| `email` | valid email; stored lowercase; globally unique |
| `password` | 8–128 chars |

**Response — `201 Created`**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": "0d5c2c9e-…",
    "email": "ada@example.com",
    "role": "owner",
    "merchant": {
      "id": "7a1f…",
      "name": "Ada's Closet",
      "slug": "ada-s-closet",
      "currency": "USD"
    }
  }
}
```

**Errors**

| Code | When |
|---|---|
| `409` | Email already registered |
| `422` | Invalid body (email format, short password, missing store name) |

**curl**

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"store_name":"Ada'"'"'s Closet","email":"ada@example.com","password":"s3cret-pass"}'
```

## `POST /auth/login`

**Request**

```json
{ "email": "ada@example.com", "password": "s3cret-pass" }
```

**Response — `200 OK`** — same shape as register (`access_token`, `token_type`, `user`).

**Errors**

| Code | When |
|---|---|
| `401` | Wrong email or password (deliberately identical message for both) |
| `422` | Invalid body |

## `GET /auth/me`

Returns the current account. Requires `Authorization: Bearer <token>`.

**Response — `200 OK`**

```json
{
  "id": "0d5c2c9e-…",
  "email": "ada@example.com",
  "role": "owner",
  "merchant": {
    "id": "7a1f…",
    "name": "Ada's Closet",
    "slug": "ada-s-closet",
    "currency": "USD"
  }
}
```

**Errors**

| Code | When |
|---|---|
| `401` | Missing, malformed, or expired token; or user no longer exists |

## Frontend notes

- Persist the token however your app prefers (localStorage is fine for v1); attach it to every
  authenticated request.
- On `401` from any endpoint, clear the token and route to `/login`.
- The `merchant.slug` is what the public chat link uses: `{FRONTEND_BASE}/chat/{slug}`.
- Registration is single-step — no email verification in v1.

## What's next (Phase 1)

Catalogue CRUD, business info, delivery zones, and settings endpoints will be added under
`/products`, `/delivery-zones`, `/business-info`, `/settings`, plus the public
`GET /public/chat/{slug}/meta`. The OpenAPI file will be regenerated when they land.
