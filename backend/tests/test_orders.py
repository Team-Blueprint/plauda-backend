import uuid
from decimal import Decimal

import pytest

from app.db.models import DeliveryZone, Product
from app.orders import service
from app.orders.errors import OrderConflictError, OrderError
from app.orders.state_machine import OrderStateError, ensure_transition
from tests.conftest import register_merchant


def test_paid_requires_webhook_trigger():
    ensure_transition("pending_payment", "paid", trigger="webhook")
    with pytest.raises(OrderStateError):
        ensure_transition("pending_payment", "paid", trigger="owner")
    with pytest.raises(OrderStateError):
        ensure_transition("pending_payment", "paid", trigger="system")


def test_terminal_states_have_no_exit():
    for terminal in ("fulfilled", "cancelled", "expired"):
        with pytest.raises(OrderStateError):
            ensure_transition(terminal, "confirmed", trigger="system")


async def _create_product(db_client, headers, *, price="25.00", variant=False):
    payload = {"name": "Scarf", "price": price}
    if variant:
        payload["variants"] = [
            {"name": "Red", "options": {"color": "red"}, "price_override": "27.50", "stock": 5}
        ]
    resp = await db_client.post("/products", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_zone(db_client, headers, *, fee="5.50"):
    resp = await db_client.post(
        "/delivery-zones",
        json={"name": "Island", "areas": ["Yaba"], "fee": fee, "eta_days": 2},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_order_lifecycle_totals_and_api(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    product = await _create_product(db_client, headers, variant=True)
    zone = await _create_zone(db_client, headers)

    order = await service.create_draft(db_session, merchant_id=merchant_id)
    item = await service.add_item(
        db_session,
        order,
        product_id=uuid.UUID(product["id"]),
        variant_id=uuid.UUID(product["variants"][0]["id"]),
        qty=2,
    )
    assert item.unit_price == Decimal("27.50")

    await service.set_delivery(
        db_session, order, zone_id=uuid.UUID(zone["id"]), address="12 Allen Avenue"
    )
    order = await service.confirm_order(db_session, order)
    assert order.status == "confirmed"
    assert order.subtotal == Decimal("55.00")
    assert order.delivery_fee == Decimal("5.50")
    assert order.total == Decimal("60.50")

    resp = await db_client.get("/orders", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "confirmed"
    assert body["items"][0]["item_count"] == 2
    assert body["items"][0]["total"] == "60.50"

    resp = await db_client.get(f"/orders/{order.id}", headers=headers)
    detail = resp.json()
    assert detail["delivery_details"]["address"] == "12 Allen Avenue"
    assert detail["items"][0]["line_total"] == "55.00"
    assert detail["items"][0]["variant_snapshot"] == {
        "name": "Red",
        "options": {"color": "red"},
    }

    resp = await db_client.post(f"/orders/{order.id}/fulfill", headers=headers)
    assert resp.status_code == 409  # only paid orders can be fulfilled

    resp = await db_client.post(f"/orders/{order.id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    resp = await db_client.post(f"/orders/{order.id}/cancel", headers=headers)
    assert resp.status_code == 409


async def test_totals_recomputed_from_catalogue_at_confirm(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    product = await _create_product(db_client, headers, price="25.00")
    zone = await _create_zone(db_client, headers, fee="5.50")

    # Cache both rows in the service session so a stale identity map would be caught.
    cached_product = await db_session.get(Product, uuid.UUID(product["id"]))
    cached_zone = await db_session.get(DeliveryZone, uuid.UUID(zone["id"]))

    order = await service.create_draft(db_session, merchant_id=merchant_id)
    await service.add_item(db_session, order, product_id=uuid.UUID(product["id"]), qty=2)
    await service.set_delivery(
        db_session, order, zone_id=uuid.UUID(zone["id"]), address="5 Marina Road"
    )

    resp = await db_client.patch(
        f"/products/{product['id']}", json={"price": "30.00"}, headers=headers
    )
    assert resp.status_code == 200
    resp = await db_client.patch(
        f"/delivery-zones/{zone['id']}", json={"fee": "7.00"}, headers=headers
    )
    assert resp.status_code == 200

    # The session still holds the old rows until confirmation refreshes them.
    assert cached_product.price == Decimal("25.00")
    assert cached_zone.fee == Decimal("5.50")

    order = await service.confirm_order(db_session, order)
    assert order.subtotal == Decimal("60.00")
    assert order.delivery_fee == Decimal("7.00")
    assert order.total == Decimal("67.00")


async def test_double_add_merges_quantity(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    product = await _create_product(db_client, headers)

    order = await service.create_draft(db_session, merchant_id=merchant_id)
    for _ in range(2):
        await service.add_item(db_session, order, product_id=uuid.UUID(product["id"]))

    assert len(order.items) == 1
    assert order.items[0].qty == 2


async def test_confirm_requires_items_and_delivery(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    product = await _create_product(db_client, headers)
    zone = await _create_zone(db_client, headers)

    order = await service.create_draft(db_session, merchant_id=merchant_id)
    with pytest.raises(OrderError, match="no items"):
        await service.confirm_order(db_session, order)

    await service.add_item(db_session, order, product_id=uuid.UUID(product["id"]))
    with pytest.raises(OrderError, match="Delivery details"):
        await service.confirm_order(db_session, order)

    await service.set_delivery(
        db_session, order, zone_id=uuid.UUID(zone["id"]), address="5 Marina Road"
    )
    order = await service.confirm_order(db_session, order)
    assert order.status == "confirmed"


async def test_payment_flow_and_owner_fulfillment(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    product = await _create_product(db_client, headers)
    zone = await _create_zone(db_client, headers)

    order = await service.create_draft(db_session, merchant_id=merchant_id)
    await service.add_item(db_session, order, product_id=uuid.UUID(product["id"]))
    await service.set_delivery(
        db_session, order, zone_id=uuid.UUID(zone["id"]), address="5 Marina Road"
    )
    order = await service.confirm_order(db_session, order)
    order = await service.mark_pending_payment(
        db_session,
        order,
        paypal_order_id="PAYPAL-1",
        approval_link="https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-1",
    )
    assert order.status == "pending_payment"

    with pytest.raises(OrderConflictError):
        await service.fulfill_order(db_session, order)

    order = await service.mark_paid(db_session, order)
    assert order.status == "paid"
    assert order.paid_at is not None

    resp = await db_client.post(f"/orders/{order.id}/fulfill", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "fulfilled"


async def test_product_with_order_history_cannot_be_deleted(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    product = await _create_product(db_client, headers)

    order = await service.create_draft(db_session, merchant_id=merchant_id)
    await service.add_item(db_session, order, product_id=uuid.UUID(product["id"]))

    resp = await db_client.delete(f"/products/{product['id']}", headers=headers)
    assert resp.status_code == 409
    assert "order history" in resp.json()["detail"]


async def test_orders_are_merchant_scoped(db_client, db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    order = await service.create_draft(db_session, merchant_id=merchant_id)

    other = await register_merchant(db_client)
    resp = await db_client.get(f"/orders/{order.id}", headers=other["headers"])
    assert resp.status_code == 404
    resp = await db_client.get("/orders", headers=other["headers"])
    assert resp.json()["total"] == 0


async def test_unknown_status_filter_is_rejected(db_client, merchant_auth):
    resp = await db_client.get("/orders?status=bogus", headers=merchant_auth["headers"])
    assert resp.status_code == 422
