# API conventions

**Base URL (dev):** `http://localhost:8000`
**API docs (dev):** `http://localhost:8000/docs`

## Authentication

All merchant-facing endpoints require a Bearer token:

```http
Authorization: Bearer <access_token>
```

- Token is returned by `POST /auth/register` and `POST /auth/login`.
- It is a JWT signed with `HS256`; expiry defaults to 24h (`JWT_EXPIRY_MINUTES`).
- No refresh token yet (planned in Phase 6 — the UI should handle a 401 by sending the user to
  login).
- Public merchant endpoints (store meta, PayPal webhooks, health) never require the header.
- Public chat thread endpoints are authenticated with the **visitor token** issued once when the
  thread is created: `Authorization: Bearer <visitor_token>`. See
  [`conversations.md`](conversations.md).

## Error format

Every error is JSON. The shape is:

```json
{ "detail": "Human-readable message" }
```

Validation errors (HTTP 422, raised by Pydantic) use FastAPI's list form:

```json
{
  "detail": [
    { "loc": ["body", "email"], "msg": "value is not a valid email address", "type": "value_error" }
  ]
}
```

Status codes used so far:

| Code | Meaning |
|---|---|
| `200` | OK |
| `201` | Created (register, thread, message, order) |
| `400` | Malformed webhook body or invalid PayPal signature |
| `401` | Missing/invalid/expired token, or bad credentials |
| `404` | Unknown resource, wrong visitor token, or another merchant's row |
| `409` | Conflict (email exists, invalid status transition, product has orders) |
| `422` | Request body/params failed validation |
| `501` | Feature not configured (e.g. PayPal credentials missing) |
| `502` | Upstream provider failure (PayPal API) |
| `500` | Unhandled server error (generic message; details stay in server logs) |

## Identifiers

- All IDs are **UUIDs** serialized as strings (`"6f1c…"`).
- Merchant `slug` is a URL-safe unique string (`ada-s-closet`). The public chat link is
  `/chat/{slug}`.

## Money

- Stored as Postgres `NUMERIC(12,2)`; serialized as **decimal strings** (`"25.00"`), never floats.
- Currency is a 3-letter ISO code from the PayPal-supported allowlist (see
  [`../contracts/enums.md`](../contracts/enums.md)). `NGN` is rejected in v1.
- The UI must render amounts as returned; never do arithmetic on the client for order totals.

## Timestamps

ISO-8601 with timezone, UTC (e.g. `"2026-10-29T18:52:00+00:00"`).

## CORS

Allowed origins are configured server-side via `CORS_ORIGINS` (JSON list, default
`["http://localhost:5173"]`). Credentials are allowed; the frontend should use the standard
Bearer-token header rather than cookies.

## Pagination

Not used yet. List endpoints added in later phases will use `limit`/`offset` with a
`{"items": [...], "total": n}` envelope. This document will be updated when the first list
endpoint ships.
