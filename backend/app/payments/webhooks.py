"""PayPal webhook dispatch. Signature verification + ``event_id`` idempotency + audit.

The capture-completed handler is the only path in the system that can move an order to ``paid``
(it calls the order service's webhook-only transition).
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations import service as conversation_service
from app.db.models import Conversation, Merchant, Message, Order, PayPalWebhookEvent
from app.orders.errors import OrderError
from app.orders.service import mark_paid
from app.payments.audit import record_action
from app.payments.errors import (
    PaymentError,
    PaymentProviderError,
    WebhookVerificationError,
)
from app.payments.paypal.client import client_for_merchant

logger = logging.getLogger(__name__)

CAPTURE_COMPLETED = "PAYMENT.CAPTURE.COMPLETED"
CAPTURE_DECLINED = frozenset({"PAYMENT.CAPTURE.DECLINED", "PAYMENT.CAPTURE.DENIED"})
CAPTURE_REFUNDED = "PAYMENT.CAPTURE.REFUNDED"
ORDER_APPROVED = "CHECKOUT.ORDER.APPROVED"


async def handle_webhook(
    session: AsyncSession,
    merchant: Merchant,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    if not isinstance(payload, dict):
        raise WebhookVerificationError("Invalid webhook payload")
    event_id = payload.get("id")
    event_type = payload.get("event_type")
    if not event_id or not event_type:
        raise PaymentError("Webhook payload is missing id or event_type")

    merchant_id = merchant.id
    client = client_for_merchant(merchant)
    if not await client.verify_webhook_signature(headers, payload):
        raise WebhookVerificationError("Invalid PayPal webhook signature")

    existing = await session.scalar(
        select(PayPalWebhookEvent).where(PayPalWebhookEvent.event_id == event_id)
    )
    if existing is not None and existing.processed_at is not None:
        return {"status": "ignored", "reason": "duplicate"}

    resource = payload.get("resource") or {}
    if existing is None:
        event = PayPalWebhookEvent(
            merchant_id=merchant_id,
            event_id=event_id,
            event_type=event_type,
            resource_id=resource.get("id"),
            payload=payload,
            signature_verified=True,
        )
        session.add(event)
        try:
            await session.commit()
        except IntegrityError:
            # Concurrent delivery of the same event.
            await session.rollback()
            existing = await session.scalar(
                select(PayPalWebhookEvent).where(PayPalWebhookEvent.event_id == event_id)
            )
            if existing is not None and existing.processed_at is not None:
                return {"status": "ignored", "reason": "duplicate"}
            if existing is None:
                raise PaymentProviderError("Could not persist the webhook event") from None
            event = existing
    else:
        event = existing

    try:
        result = await _dispatch(session, merchant_id, event_id, event_type, resource)
    except Exception:
        await session.rollback()
        logger.exception("PayPal webhook dispatch failed for event %s", event_id)
        raise PaymentProviderError("Webhook processing failed") from None

    event.processed_at = datetime.now(UTC)
    await session.commit()
    return {"status": "processed", "event_type": event_type, "result": result}


async def _dispatch(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    event_id: str,
    event_type: str,
    resource: dict,
) -> str:
    if event_type == ORDER_APPROVED:
        return await _handle_order_approved(session, merchant_id, event_id, resource)
    if event_type == CAPTURE_COMPLETED:
        return await _handle_capture_completed(session, merchant_id, event_id, resource)
    if event_type in CAPTURE_DECLINED:
        return await _handle_capture_declined(session, merchant_id, event_id, resource)
    if event_type == CAPTURE_REFUNDED:
        return await _handle_refund(session, merchant_id, event_id, resource)
    # Everything else: recorded, no state change.
    return "ignored"


async def _find_order(
    session: AsyncSession, merchant_id: uuid.UUID, resource: dict
) -> Order | None:
    related = (resource.get("supplementary_data") or {}).get("related_ids") or {}
    paypal_order_id = related.get("order_id")
    if not paypal_order_id:
        return None
    return await _find_order_by_paypal_id(session, merchant_id, paypal_order_id)


async def _find_order_by_paypal_id(
    session: AsyncSession, merchant_id: uuid.UUID, paypal_order_id: str
) -> Order | None:
    return await session.scalar(
        select(Order).where(
            Order.paypal_order_id == paypal_order_id,
            Order.merchant_id == merchant_id,
        )
    )


async def _handle_order_approved(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    event_id: str,
    resource: dict,
) -> str:
    """Capture the approved PayPal order; ``capture.completed`` still marks it paid."""
    paypal_order_id = resource.get("id")
    if not paypal_order_id:
        return "ignored"
    order = await _find_order_by_paypal_id(session, merchant_id, paypal_order_id)
    if order is None or order.status != "pending_payment":
        return "ignored"

    merchant = await session.get(Merchant, merchant_id)
    if merchant is None:
        return "ignored"
    client = client_for_merchant(merchant)
    capture = await client.capture_order(paypal_order_id)

    await record_action(
        session,
        merchant_id=merchant_id,
        order_id=order.id,
        action="mark_paid",
        trigger="webhook",
        amount=order.total,
        result="success",
        detail={
            "step": "capture_requested",
            "paypal_order_id": paypal_order_id,
            "capture_status": capture.get("status"),
            "already_captured": bool(capture.get("already_captured")),
            "event_id": event_id,
        },
    )
    await session.commit()
    return "processed"


def _resource_amount(resource: dict) -> Decimal | None:
    value = (resource.get("amount") or {}).get("value")
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


async def _post_system_once(
    session: AsyncSession,
    order: Order,
    *,
    event_id: str,
    kind: str,
    content: str,
) -> None:
    if order.conversation_id is None:
        return
    conversation = await session.get(Conversation, order.conversation_id)
    if conversation is None:
        return
    exists = await session.scalar(
        select(Message.id)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == "system",
            Message.meta["event_id"].astext == event_id,
        )
        .limit(1)
    )
    if exists is not None:
        return
    await conversation_service.add_message(
        session,
        conversation,
        role="system",
        content=content,
        meta={"kind": kind, "event_id": event_id, "order_id": str(order.id)},
    )


async def _handle_capture_completed(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    event_id: str,
    resource: dict,
) -> str:
    order = await _find_order(session, merchant_id, resource)
    if order is None:
        logger.warning("capture.completed for unknown PayPal order: %s", resource.get("id"))
        return "ignored"

    amount = _resource_amount(resource)
    currency = (resource.get("amount") or {}).get("currency_code")
    mismatch = (amount is not None and order.total is not None and amount != order.total) or (
        currency is not None and currency != order.currency
    )
    if mismatch:
        await record_action(
            session,
            merchant_id=merchant_id,
            order_id=order.id,
            action="mark_paid",
            trigger="webhook",
            amount=amount,
            result="ignored",
            detail={
                "reason": "amount_mismatch",
                "captured_amount": str(amount),
                "captured_currency": currency,
                "expected_amount": str(order.total),
                "expected_currency": order.currency,
                "capture_id": resource.get("id"),
            },
        )
        await session.commit()
        logger.warning(
            "capture.completed amount mismatch for order %s: %s %s != %s %s",
            order.id,
            amount,
            currency,
            order.total,
            order.currency,
        )
        return "ignored"

    if order.status == "pending_payment":
        try:
            order = await mark_paid(session, order)
        except OrderError:
            logger.warning("capture.completed for order %s in status %s", order.id, order.status)
            return "ignored"
    elif order.status != "paid":
        await record_action(
            session,
            merchant_id=merchant_id,
            order_id=order.id,
            action="mark_paid",
            trigger="webhook",
            amount=amount,
            result="ignored",
            detail={"order_status": order.status, "capture_id": resource.get("id")},
        )
        await session.commit()
        return "ignored"

    await record_action(
        session,
        merchant_id=merchant_id,
        order_id=order.id,
        action="mark_paid",
        trigger="webhook",
        amount=amount or order.total,
        result="success",
        detail={"capture_id": resource.get("id")},
    )
    await session.commit()
    await _post_system_once(
        session,
        order,
        event_id=event_id,
        kind="payment",
        content="Payment received — your order is confirmed.",
    )
    return "processed"


async def _handle_capture_declined(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    event_id: str,
    resource: dict,
) -> str:
    order = await _find_order(session, merchant_id, resource)
    if order is None:
        return "ignored"

    await record_action(
        session,
        merchant_id=merchant_id,
        order_id=order.id,
        action="mark_paid",
        trigger="webhook",
        amount=_resource_amount(resource),
        result="declined",
        detail={"capture_id": resource.get("id"), "order_status": order.status},
    )
    await session.commit()
    await _post_system_once(
        session,
        order,
        event_id=event_id,
        kind="payment",
        content="Payment was declined — the order is still awaiting payment.",
    )
    return "processed"


async def _handle_refund(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    event_id: str,
    resource: dict,
) -> str:
    order = await _find_order(session, merchant_id, resource)
    if order is None:
        return "ignored"

    await record_action(
        session,
        merchant_id=merchant_id,
        order_id=order.id,
        action="refund",
        trigger="webhook",
        amount=_resource_amount(resource),
        result="success",
        detail={"refund_id": resource.get("id"), "event_id": event_id},
    )
    await session.commit()
    return "processed"
