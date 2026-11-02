import json
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.models import (
    Conversation,
    Merchant,
    Message,
    Order,
    PaymentAction,
    PayPalWebhookEvent,
)
from app.orders import service as order_service
from app.payments import service as payment_service
from app.payments.crypto import decrypt_secret, encrypt_secret
from app.payments.errors import (
    CredentialError,
    PaymentProviderError,
    PayPalNotConfiguredError,
)
from app.payments.paypal.client import PayPalClient, extract_approval_link
from tests.conftest import register_merchant


@pytest.fixture
def encryption_key(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_crypto_roundtrip(encryption_key):
    token = encrypt_secret("super-secret")
    assert token != "super-secret"
    assert decrypt_secret(token) == "super-secret"


def test_crypto_requires_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(CredentialError):
            encrypt_secret("x")
    finally:
        get_settings.cache_clear()


async def test_paypal_client_create_order_and_verify_webhook():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "token-1"})
        if request.url.path == "/v2/checkout/orders":
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": "PAYPAL-ORDER-1",
                    "links": [{"rel": "approve", "href": "https://paypal.example/approve"}],
                },
            )
        if request.url.path == "/v1/notifications/verify-webhook-signature":
            seen["verify"] = json.loads(request.content)
            return httpx.Response(200, json={"verification_status": "SUCCESS"})
        return httpx.Response(404)

    client = PayPalClient(
        client_id="id",
        client_secret="secret",
        env="sandbox",
        webhook_id="WH-1",
        transport=httpx.MockTransport(handler),
    )

    paypal_order = await client.create_order(
        reference_id="order-1",
        amount=Decimal("60.50"),
        currency="USD",
        return_url="https://shop/return",
        cancel_url="https://shop/cancel",
    )
    assert paypal_order["id"] == "PAYPAL-ORDER-1"
    assert extract_approval_link(paypal_order) == "https://paypal.example/approve"

    body = seen["body"]
    assert body["intent"] == "CAPTURE"
    assert body["purchase_units"][0]["reference_id"] == "order-1"
    assert body["purchase_units"][0]["amount"] == {
        "currency_code": "USD",
        "value": "60.50",
    }
    assert body["application_context"]["return_url"] == "https://shop/return"

    headers = {
        "paypal-transmission-id": "t",
        "paypal-transmission-time": "2026-01-01T00:00:00Z",
        "paypal-cert-url": "https://cert",
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-transmission-sig": "sig",
    }
    assert await client.verify_webhook_signature(headers, {"id": "evt"}) is True
    assert seen["verify"]["webhook_id"] == "WH-1"
    assert seen["verify"]["webhook_event"] == {"id": "evt"}


async def test_paypal_client_rejects_bad_credentials():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    client = PayPalClient(
        client_id="id",
        client_secret="bad",
        env="sandbox",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(PaymentProviderError):
        await client.check_credentials()


async def test_paypal_capture_already_captured_is_idempotent():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "token-1"})
        if request.url.path.endswith("/capture"):
            return httpx.Response(
                422,
                json={
                    "name": "UNPROCESSABLE_ENTITY",
                    "details": [{"issue": "ORDER_ALREADY_CAPTURED"}],
                },
            )
        return httpx.Response(404)

    client = PayPalClient(
        client_id="id",
        client_secret="secret",
        env="sandbox",
        transport=httpx.MockTransport(handler),
    )
    assert await client.capture_order("PAYPAL-1") == {
        "status": "COMPLETED",
        "already_captured": True,
    }


async def test_verify_without_webhook_id_is_false():
    client = PayPalClient(client_id="id", client_secret="secret", env="sandbox")
    assert await client.verify_webhook_signature({}, {}) is False


class _FakePayPalClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def check_credentials(self) -> None:
        return None


class _RejectingPayPalClient(_FakePayPalClient):
    async def check_credentials(self) -> None:
        raise PaymentProviderError("bad credentials")


async def test_paypal_credentials_connect_and_disconnect(
    db_client, db_session, merchant_auth, encryption_key, monkeypatch
):
    monkeypatch.setattr("app.payments.routes.PayPalClient", _FakePayPalClient)
    headers = merchant_auth["headers"]
    payload = {
        "client_id": "client-1",
        "client_secret": "secret-1",
        "webhook_id": "WH-1",
        "env": "sandbox",
    }

    resp = await db_client.post("/settings/paypal", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"connected": True, "env": "sandbox"}

    resp = await db_client.get("/settings", headers=headers)
    assert resp.json()["paypal_connected"] is True
    assert "secret-1" not in resp.text

    merchant = await db_session.get(Merchant, uuid.UUID(merchant_auth["merchant"]["id"]))
    assert merchant.paypal_client_id_enc != "client-1"
    assert decrypt_secret(merchant.paypal_client_id_enc) == "client-1"
    assert decrypt_secret(merchant.paypal_webhook_id_enc) == "WH-1"

    resp = await db_client.delete("/settings/paypal", headers=headers)
    assert resp.status_code == 204
    resp = await db_client.get("/settings/paypal", headers=headers)
    assert resp.json() == {"connected": False, "env": None}


async def test_paypal_credentials_rejected(db_client, merchant_auth, encryption_key, monkeypatch):
    monkeypatch.setattr("app.payments.routes.PayPalClient", _RejectingPayPalClient)
    resp = await db_client.post(
        "/settings/paypal",
        json={
            "client_id": "client-1",
            "client_secret": "secret-1",
            "webhook_id": "WH-1",
            "env": "sandbox",
        },
        headers=merchant_auth["headers"],
    )
    assert resp.status_code == 422


async def _confirmed_order(
    db_client, db_session, merchant_auth, *, conversation_id=None, customer_id=None
) -> Order:
    headers = merchant_auth["headers"]
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])

    resp = await db_client.post(
        "/products", json={"name": "Scarf", "price": "55.00"}, headers=headers
    )
    product = resp.json()
    resp = await db_client.post(
        "/delivery-zones",
        json={"name": "Island", "areas": ["Yaba"], "fee": "5.50", "eta_days": 2},
        headers=headers,
    )
    zone = resp.json()

    order = await order_service.create_draft(
        db_session,
        merchant_id=merchant_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
    )
    await order_service.add_item(db_session, order, product_id=uuid.UUID(product["id"]), qty=1)
    await order_service.set_delivery(
        db_session, order, zone_id=uuid.UUID(zone["id"]), address="12 Allen Avenue"
    )
    return await order_service.confirm_order(db_session, order)


class _FakeWebhookClient:
    def __init__(self, verified: bool = True) -> None:
        self.verified = verified

    async def verify_webhook_signature(self, headers, event) -> bool:
        return self.verified


def _capture_event(paypal_order_id: str, event_id: str | None = None) -> dict:
    return {
        "id": event_id or f"WH-{uuid.uuid4().hex}",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": f"CAP-{uuid.uuid4().hex[:8]}",
            "amount": {"value": "60.50", "currency_code": "USD"},
            "supplementary_data": {"related_ids": {"order_id": paypal_order_id}},
        },
    }


class _FakeCaptureClient:
    def __init__(self) -> None:
        self.calls = 0

    async def verify_webhook_signature(self, headers, event) -> bool:
        return True

    async def capture_order(self, order_id: str) -> dict:
        self.calls += 1
        return {"status": "COMPLETED"}


async def test_order_approved_triggers_capture_once(
    db_client, db_session, merchant_auth, monkeypatch
):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    order = await _confirmed_order(db_client, db_session, merchant_auth)
    order = await order_service.mark_pending_payment(
        db_session,
        order,
        paypal_order_id="PAYPAL-APPROVED",
        approval_link="https://paypal.example/approve",
    )

    fake = _FakeCaptureClient()
    monkeypatch.setattr("app.payments.webhooks.client_for_merchant", lambda merchant: fake)
    event = {
        "id": f"WH-{uuid.uuid4().hex}",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {"id": "PAYPAL-APPROVED"},
    }

    resp = await db_client.post(f"/webhooks/paypal/{merchant_id}", json=event)
    assert resp.status_code == 200
    assert resp.json()["result"] == "processed"
    assert fake.calls == 1

    await db_session.refresh(order)
    assert order.status == "pending_payment"

    action = await db_session.scalar(
        select(PaymentAction).where(PaymentAction.order_id == order.id)
    )
    assert action.detail["step"] == "capture_requested"

    # The same event is not captured twice.
    resp = await db_client.post(f"/webhooks/paypal/{merchant_id}", json=event)
    assert resp.json()["status"] == "ignored"
    assert fake.calls == 1


async def test_webhook_marks_order_paid_once(db_client, db_session, merchant_auth, monkeypatch):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    created = await db_client.post(
        f"/public/chat/{merchant_auth['merchant']['slug']}/conversations"
    )
    conversation = await db_session.get(Conversation, uuid.UUID(created.json()["conversation_id"]))
    order = await _confirmed_order(
        db_client,
        db_session,
        merchant_auth,
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
    )
    order = await order_service.mark_pending_payment(
        db_session,
        order,
        paypal_order_id="PAYPAL-1",
        approval_link="https://paypal.example/approve",
    )

    monkeypatch.setattr(
        "app.payments.webhooks.client_for_merchant",
        lambda merchant: _FakeWebhookClient(True),
    )
    event = _capture_event("PAYPAL-1")

    resp = await db_client.post(f"/webhooks/paypal/{merchant_id}", json=event)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "status": "processed",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "result": "processed",
    }

    await db_session.refresh(order)
    assert order.status == "paid"
    assert order.paid_at is not None

    actions = (
        await db_session.scalars(select(PaymentAction).where(PaymentAction.order_id == order.id))
    ).all()
    assert len(actions) == 1
    assert actions[0].action == "mark_paid"
    assert actions[0].trigger == "webhook"
    assert actions[0].amount == Decimal("60.50")

    messages = (
        await db_session.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id, Message.role == "system"
            )
        )
    ).all()
    assert any(message.meta.get("kind") == "payment" for message in messages)

    # Duplicate delivery is acknowledged but does nothing.
    resp = await db_client.post(f"/webhooks/paypal/{merchant_id}", json=event)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

    order_id = order.id
    conversation_id = conversation.id
    db_session.expire_all()
    actions = (
        await db_session.scalars(select(PaymentAction).where(PaymentAction.order_id == order_id))
    ).all()
    assert len(actions) == 1

    receipts = (
        await db_session.scalars(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.role == "system",
                Message.meta["event_id"].astext == event["id"],
            )
        )
    ).all()
    assert len(receipts) == 1


async def test_webhook_ignores_amount_mismatch(db_client, db_session, merchant_auth, monkeypatch):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    order = await _confirmed_order(db_client, db_session, merchant_auth)
    order = await order_service.mark_pending_payment(
        db_session,
        order,
        paypal_order_id="PAYPAL-MISMATCH",
        approval_link="https://paypal.example/approve",
    )

    monkeypatch.setattr(
        "app.payments.webhooks.client_for_merchant",
        lambda merchant: _FakeWebhookClient(True),
    )
    event = _capture_event("PAYPAL-MISMATCH")
    event["resource"]["amount"]["value"] = "1.00"

    resp = await db_client.post(f"/webhooks/paypal/{merchant_id}", json=event)
    assert resp.status_code == 200
    assert resp.json()["result"] == "ignored"

    await db_session.refresh(order)
    assert order.status == "pending_payment"
    action = await db_session.scalar(
        select(PaymentAction).where(PaymentAction.order_id == order.id)
    )
    assert action.result == "ignored"
    assert action.detail["reason"] == "amount_mismatch"


async def test_webhook_declined_keeps_order_pending_and_notifies_chat(
    db_client, db_session, merchant_auth, monkeypatch
):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    created = await db_client.post(
        f"/public/chat/{merchant_auth['merchant']['slug']}/conversations"
    )
    conversation = await db_session.get(Conversation, uuid.UUID(created.json()["conversation_id"]))
    order = await _confirmed_order(
        db_client,
        db_session,
        merchant_auth,
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
    )
    order = await order_service.mark_pending_payment(
        db_session,
        order,
        paypal_order_id="PAYPAL-DECLINED",
        approval_link="https://paypal.example/approve",
    )

    monkeypatch.setattr(
        "app.payments.webhooks.client_for_merchant",
        lambda merchant: _FakeWebhookClient(True),
    )
    event = {
        "id": f"WH-{uuid.uuid4().hex}",
        "event_type": "PAYMENT.CAPTURE.DECLINED",
        "resource": {
            "id": "CAP-DECLINED",
            "amount": {"value": "60.50", "currency_code": "USD"},
            "supplementary_data": {"related_ids": {"order_id": "PAYPAL-DECLINED"}},
        },
    }

    resp = await db_client.post(f"/webhooks/paypal/{merchant_id}", json=event)
    assert resp.status_code == 200
    assert resp.json()["result"] == "processed"

    await db_session.refresh(order)
    assert order.status == "pending_payment"
    action = await db_session.scalar(
        select(PaymentAction).where(PaymentAction.order_id == order.id)
    )
    assert action.result == "declined"

    messages = (
        await db_session.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id, Message.role == "system"
            )
        )
    ).all()
    assert any("declined" in message.content for message in messages)


async def test_webhook_rejects_bad_signature(db_client, db_session, merchant_auth, monkeypatch):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    order = await _confirmed_order(db_client, db_session, merchant_auth)
    order = await order_service.mark_pending_payment(
        db_session,
        order,
        paypal_order_id="PAYPAL-BAD",
        approval_link="https://paypal.example/approve",
    )

    monkeypatch.setattr(
        "app.payments.webhooks.client_for_merchant",
        lambda merchant: _FakeWebhookClient(False),
    )
    resp = await db_client.post(
        f"/webhooks/paypal/{merchant_id}", json=_capture_event("PAYPAL-BAD")
    )
    assert resp.status_code == 400

    await db_session.refresh(order)
    assert order.status == "pending_payment"
    events = (
        await db_session.scalars(
            select(PayPalWebhookEvent).where(PayPalWebhookEvent.merchant_id == merchant_id)
        )
    ).all()
    assert events == []


async def test_webhook_unknown_merchant(db_client):
    resp = await db_client.post(f"/webhooks/paypal/{uuid.uuid4()}", json={})
    assert resp.status_code == 404


async def test_webhook_requires_paypal_credentials(db_client, merchant_auth):
    resp = await db_client.post(
        f"/webhooks/paypal/{merchant_auth['merchant']['id']}",
        json=_capture_event("PAYPAL-NOT-CONNECTED"),
    )
    assert resp.status_code == 501


class _FakeCreateClient:
    def __init__(self) -> None:
        self.kwargs: dict | None = None
        self.calls = 0

    async def create_order(self, **kwargs) -> dict:
        self.calls += 1
        self.kwargs = kwargs
        return {
            "id": "PAYPAL-2",
            "links": [{"rel": "approve", "href": "https://paypal.example/approve/2"}],
        }


async def test_create_payment_link_moves_order_to_pending(db_client, db_session, merchant_auth):
    order = await _confirmed_order(db_client, db_session, merchant_auth)
    fake = _FakeCreateClient()

    order = await payment_service.create_payment_link_for_order(
        db_session, order, client=fake, trigger="agent"
    )
    assert order.status == "pending_payment"
    assert order.paypal_order_id == "PAYPAL-2"
    assert order.approval_link == "https://paypal.example/approve/2"
    assert order.expires_at is not None
    assert fake.kwargs is not None
    assert fake.kwargs["amount"] == Decimal("60.50")
    assert fake.kwargs["currency"] == "USD"

    action = await db_session.scalar(
        select(PaymentAction).where(PaymentAction.order_id == order.id)
    )
    assert action.action == "create_link"
    assert action.trigger == "agent"


async def test_create_payment_link_requires_credentials(db_client, db_session, merchant_auth):
    order = await _confirmed_order(db_client, db_session, merchant_auth)
    with pytest.raises(PayPalNotConfiguredError):
        await payment_service.create_payment_link_for_order(db_session, order)


async def test_owner_payment_link_endpoint_is_idempotent(
    db_client, db_session, merchant_auth, monkeypatch
):
    order = await _confirmed_order(db_client, db_session, merchant_auth)
    fake = _FakeCreateClient()
    monkeypatch.setattr("app.payments.service.client_for_merchant", lambda merchant: fake)
    headers = merchant_auth["headers"]

    first = await db_client.post(f"/orders/{order.id}/payment-link", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending_payment"
    assert first.json()["paypal_order_id"] == "PAYPAL-2"
    assert first.json()["approval_link"] == "https://paypal.example/approve/2"
    assert first.json()["expires_at"] is not None

    second = await db_client.post(f"/orders/{order.id}/payment-link", headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["approval_link"] == "https://paypal.example/approve/2"
    assert fake.calls == 1

    action = await db_session.scalar(
        select(PaymentAction).where(PaymentAction.order_id == order.id)
    )
    assert action.action == "create_link"
    assert action.trigger == "staff"


async def test_payment_link_requires_confirmed_order(db_client, db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    order = await order_service.create_draft(db_session, merchant_id=merchant_id)

    resp = await db_client.post(
        f"/orders/{order.id}/payment-link", headers=merchant_auth["headers"]
    )
    assert resp.status_code == 409


async def test_payment_link_is_tenant_scoped(db_client, db_session, merchant_auth):
    order = await _confirmed_order(db_client, db_session, merchant_auth)
    other = await register_merchant(db_client)

    resp = await db_client.post(f"/orders/{order.id}/payment-link", headers=other["headers"])
    assert resp.status_code == 404
