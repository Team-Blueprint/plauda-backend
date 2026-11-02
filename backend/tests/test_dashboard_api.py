import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

from app.db.models import Conversation, Order, PaymentAction
from tests.conftest import register_merchant


async def _make_order(
    session,
    merchant_id: uuid.UUID,
    *,
    status: str,
    total: str,
    created_at: datetime,
    paid_at: datetime | None = None,
) -> Order:
    order = Order(
        merchant_id=merchant_id,
        status=status,
        currency="USD",
        subtotal=Decimal(total),
        delivery_fee=Decimal("0.00"),
        total=Decimal(total),
        created_at=created_at,
        paid_at=paid_at,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def _make_conversation(
    session, merchant_id: uuid.UUID, *, status: str, started_at: datetime
) -> Conversation:
    conversation = Conversation(
        merchant_id=merchant_id,
        status=status,
        started_at=started_at,
        created_at=started_at,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def test_dashboard_summary_reports_today_and_live_chats(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today_start - timedelta(hours=1)

    await _make_order(
        db_session,
        merchant_id,
        status="paid",
        total="10.00",
        created_at=now,
        paid_at=now,
    )
    await _make_order(
        db_session,
        merchant_id,
        status="fulfilled",
        total="5.00",
        created_at=now,
        paid_at=now,
    )
    await _make_order(
        db_session,
        merchant_id,
        status="pending_payment",
        total="7.00",
        created_at=now,
    )
    await _make_order(
        db_session,
        merchant_id,
        status="cancelled",
        total="9.00",
        created_at=now,
    )
    await _make_order(
        db_session,
        merchant_id,
        status="paid",
        total="20.00",
        created_at=yesterday,
        paid_at=yesterday,
    )
    # Revenue follows paid_at, not created_at.
    await _make_order(
        db_session,
        merchant_id,
        status="paid",
        total="20.00",
        created_at=yesterday,
        paid_at=now,
    )

    for status in ("ai", "handoff_requested", "human_active", "closed"):
        await _make_conversation(db_session, merchant_id, status=status, started_at=now)

    resp = await db_client.get("/dashboard/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["currency"] == "USD"
    assert body["revenue_today"] == "35.00"
    assert body["orders_today"] == 4
    assert body["paid_orders_today"] == 3
    assert body["pending_payment_orders"] == 1
    assert body["live_chats"] == 3
    assert body["handoff_requests"] == 1
    assert body["total_revenue"] == "55.00"
    assert body["total_orders"] == 6
    assert datetime.fromisoformat(body["day_start"].replace("Z", "+00:00")) == today_start


async def test_dashboard_summary_is_tenant_scoped(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    now = datetime.now(UTC)

    other = await register_merchant(db_client)
    other_id = uuid.UUID(other["merchant"]["id"])
    await _make_order(
        db_session,
        other_id,
        status="paid",
        total="999.00",
        created_at=now,
        paid_at=now,
    )
    await _make_conversation(db_session, other_id, status="ai", started_at=now)

    resp = await db_client.get("/dashboard/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["revenue_today"] == "0.00"
    assert body["orders_today"] == 0
    assert body["paid_orders_today"] == 0
    assert body["pending_payment_orders"] == 0
    assert body["live_chats"] == 0
    assert body["handoff_requests"] == 0
    assert body["total_revenue"] == "0.00"
    assert body["total_orders"] == 0


async def test_audit_lists_tenant_actions_with_filters(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    now = datetime.now(UTC)

    order = await _make_order(
        db_session,
        merchant_id,
        status="paid",
        total="10.00",
        created_at=now,
        paid_at=now,
    )
    other_order = await _make_order(
        db_session,
        merchant_id,
        status="pending_payment",
        total="4.00",
        created_at=now,
    )

    other = await register_merchant(db_client)
    other_id = uuid.UUID(other["merchant"]["id"])
    other_merchant_order = await _make_order(
        db_session,
        other_id,
        status="paid",
        total="999.00",
        created_at=now,
        paid_at=now,
    )

    actions = [
        PaymentAction(
            merchant_id=merchant_id,
            order_id=order.id,
            action="create_link",
            trigger="staff",
            amount=Decimal("10.00"),
            result="success",
            detail={"paypal_order_id": "PAYPAL-1"},
            created_at=now - timedelta(minutes=3),
        ),
        PaymentAction(
            merchant_id=merchant_id,
            order_id=order.id,
            action="mark_paid",
            trigger="webhook",
            amount=Decimal("10.00"),
            result="success",
            detail={"capture_id": "CAPTURE-1"},
            created_at=now - timedelta(minutes=2),
        ),
        PaymentAction(
            merchant_id=merchant_id,
            order_id=other_order.id,
            action="refund",
            trigger="staff",
            amount=Decimal("3.00"),
            result="declined",
            detail={"reason": "test"},
            created_at=now - timedelta(minutes=1),
        ),
        PaymentAction(
            merchant_id=other_id,
            order_id=other_merchant_order.id,
            action="mark_paid",
            trigger="webhook",
            amount=Decimal("999.00"),
            result="success",
            detail={},
            created_at=now,
        ),
    ]
    db_session.add_all(actions)
    await db_session.commit()

    resp = await db_client.get("/audit", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["items"][0]["action"] == "refund"
    assert body["items"][0]["order_status"] == "pending_payment"
    assert body["items"][0]["currency"] == "USD"
    assert body["items"][1]["action"] == "mark_paid"
    assert body["items"][2]["action"] == "create_link"

    resp = await db_client.get("/audit?action=mark_paid", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["detail"] == {"capture_id": "CAPTURE-1"}

    resp = await db_client.get(f"/audit?order_id={order.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 2

    resp = await db_client.get("/audit?trigger=staff", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 2

    resp = await db_client.get("/audit?result=declined", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 1

    since = quote((now - timedelta(minutes=2, seconds=30)).isoformat(), safe="")
    resp = await db_client.get(f"/audit?since={since}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 2

    resp = await db_client.get("/audit?limit=1&offset=1", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "mark_paid"


async def test_audit_requires_auth_and_rejects_invalid_filters(db_client, merchant_auth):
    resp = await db_client.get("/audit")
    assert resp.status_code == 401

    resp = await db_client.get("/audit?action=bogus", headers=merchant_auth["headers"])
    assert resp.status_code == 422

    now = datetime.now(UTC)
    since = quote((now + timedelta(minutes=1)).isoformat(), safe="")
    until = quote((now - timedelta(minutes=1)).isoformat(), safe="")
    resp = await db_client.get(
        f"/audit?since={since}&until={until}", headers=merchant_auth["headers"]
    )
    assert resp.status_code == 422
