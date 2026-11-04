from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Merchant, Order
from app.orders.events import publish_order_update
from app.orders.service import mark_pending_payment, money
from app.payments.audit import record_action
from app.payments.errors import (
    PaymentConflictError,
    PaymentError,
    PaymentProviderError,
)
from app.payments.paypal.client import (
    PayPalClient,
    client_for_merchant,
    extract_approval_link,
)


async def create_payment_link_for_order(
    session: AsyncSession,
    order: Order,
    *,
    return_url: str | None = None,
    cancel_url: str | None = None,
    client: PayPalClient | None = None,
    trigger: str = "system",
) -> Order:
    """Create a PayPal order for a confirmed order and move it to ``pending_payment``.

    The future ``create_payment_link`` agent tool calls this; the audit trigger should then
    be ``agent``. Amounts always come from the server-owned order total.
    """
    if order.status != "confirmed":
        raise PaymentConflictError("Only a confirmed order can request payment")
    if order.total is None or order.total <= 0:
        raise PaymentError("Order total must be positive")

    merchant = await session.get(Merchant, order.merchant_id)
    if merchant is None:
        raise PaymentError("Merchant not found")
    if client is None:
        client = client_for_merchant(merchant)

    settings = get_settings()
    frontend = settings.frontend_base_url.rstrip("/")
    return_url = return_url or f"{frontend}/checkout/result?order_id={order.id}"
    cancel_url = cancel_url or (f"{frontend}/checkout/result?order_id={order.id}&status=cancel")

    paypal_order = await client.create_order(
        reference_id=str(order.id),
        amount=money(order.total),
        currency=order.currency,
        return_url=return_url,
        cancel_url=cancel_url,
    )
    paypal_order_id = paypal_order.get("id")
    approval_link = extract_approval_link(paypal_order)
    if not paypal_order_id or not approval_link:
        raise PaymentProviderError("PayPal did not return an approval link")

    expires_at = datetime.now(UTC) + timedelta(minutes=merchant.recovery_timeout_minutes)
    order = await mark_pending_payment(
        session,
        order,
        paypal_order_id=paypal_order_id,
        approval_link=approval_link,
        expires_at=expires_at,
    )
    await record_action(
        session,
        merchant_id=order.merchant_id,
        order_id=order.id,
        action="create_link",
        trigger=trigger,
        amount=order.total,
        result="success",
        detail={"paypal_order_id": paypal_order_id},
    )
    await session.commit()
    publish_order_update(order)
    return order
