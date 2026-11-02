# Dashboard & audit API

**Status:** Phase 5 backend — revenue summary and payment audit are implemented. Refunds and the
recovery worker are later Phase 5 work.

Both endpoints require `Authorization: Bearer <token>` and only read the caller's merchant data.

## `GET /dashboard/summary`

Returns the numbers the operations dashboard needs. The day window is **UTC**:

- starts at `00:00:00Z` on the current UTC date
- ends at the next UTC midnight

```json
{
  "as_of": "2026-11-02T14:30:00Z",
  "day_start": "2026-11-02T00:00:00Z",
  "currency": "USD",
  "revenue_today": "15.00",
  "orders_today": 4,
  "paid_orders_today": 2,
  "pending_payment_orders": 1,
  "live_chats": 3,
  "handoff_requests": 1,
  "total_revenue": "35.00",
  "total_orders": 5
}
```

| Field | Meaning |
|---|---|
| `as_of` | Server time when the summary was calculated |
| `day_start` | Start of the UTC day used for the `*_today` fields |
| `currency` | Merchant currency |
| `revenue_today` | Sum of `total` for `paid`/`fulfilled` orders whose `paid_at` is in the day window |
| `orders_today` | Orders created in the day window, all statuses |
| `paid_orders_today` | Orders whose `paid_at` is in the day window (paid or fulfilled) |
| `pending_payment_orders` | Current snapshot of orders in `pending_payment` |
| `live_chats` | Current conversations in `ai`, `handoff_requested`, or `human_active` |
| `handoff_requests` | Current conversations waiting for owner acceptance |
| `total_revenue` | Lifetime sum of `total` for `paid`/`fulfilled` orders |
| `total_orders` | Lifetime order count, all statuses |

Money fields are decimal **strings**. Empty sums return `"0.00"`. Revenue is gross captured sales;
the refund flow is not built yet, so refunds are not netted out of these totals.

## `GET /audit`

Paginated payment audit trail. One row is written for every money-touching action:
link creation, capture/mark-paid, refund, receipt, and expiry.

### Query parameters

| Name | Type | Default | Notes |
|---|---|---|---|
| `order_id` | UUID | — | Only actions for one order |
| `action` | enum | — | `create_link` · `refund` · `mark_paid` · `receipt` · `expire` |
| `trigger` | enum | — | `agent` · `webhook` · `staff` · `system` |
| `result` | enum | — | `success` · `declined` · `ignored` · `failed` |
| `since` | ISO-8601 datetime | — | Inclusive lower bound on `created_at` |
| `until` | ISO-8601 datetime | — | Inclusive upper bound on `created_at` |
| `limit` | int | `50` | 1–100 |
| `offset` | int | `0` | ≥ 0 |

`since` and `until` are normalized to UTC. A naive datetime is treated as UTC. A range where
`since > until` returns `422`.

### Response

Newest actions first.

```json
{
  "items": [
    {
      "id": "d0e9f4c1-7e0e-4d7d-9f6a-8a5f0d7f2e21",
      "order_id": "3f1c8a46-8f4a-4f4d-9c2c-1c9c0a3f5b77",
      "order_status": "paid",
      "currency": "USD",
      "action": "mark_paid",
      "trigger": "webhook",
      "amount": "10.00",
      "result": "success",
      "detail": {
        "capture_id": "1EA58572KJ470073T"
      },
      "created_at": "2026-11-02T13:13:58Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

`amount` is in the order's `currency` and may be `null` for non-money events such as a receipt.
`detail` contains provider identifiers and diagnostic context. Audit rows are immutable; there
are no create, update, or delete endpoints.

## Errors

| Status | Meaning |
|---|---|
| `401` | Missing or invalid bearer token |
| `422` | Invalid enum value, UUID, datetime, pagination, or date range |
