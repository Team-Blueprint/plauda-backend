import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DeliveryZone, Merchant, Order, OrderItem, Product, ProductVariant
from app.orders.errors import OrderConflictError, OrderError, OrderNotFoundError
from app.orders.state_machine import OrderStateError, ensure_transition

CENT = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _transition(order: Order, new: str, *, trigger: str) -> None:
    try:
        ensure_transition(order.status, new, trigger=trigger)
    except OrderStateError as exc:
        raise OrderConflictError(str(exc)) from exc
    order.status = new


async def get_order(session: AsyncSession, merchant_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    order = await session.scalar(
        select(Order).where(Order.id == order_id, Order.merchant_id == merchant_id)
    )
    if order is None:
        raise OrderNotFoundError("Order not found")
    return order


async def create_draft(
    session: AsyncSession,
    *,
    merchant_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
) -> Order:
    merchant = await session.get(Merchant, merchant_id)
    if merchant is None:
        raise OrderNotFoundError("Merchant not found")
    order = Order(
        merchant_id=merchant_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        status="draft",
        currency=merchant.currency,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def add_item(
    session: AsyncSession,
    order: Order,
    *,
    product_id: uuid.UUID,
    variant_id: uuid.UUID | None = None,
    qty: int = 1,
) -> OrderItem:
    if order.status != "draft":
        raise OrderConflictError("Items can only be added to a draft order")
    if qty < 1:
        raise OrderError("Quantity must be at least 1")

    product = await session.scalar(
        select(Product)
        .where(Product.id == product_id, Product.merchant_id == order.merchant_id)
        .execution_options(populate_existing=True)
    )
    if product is None:
        raise OrderNotFoundError("Product not found")
    if not product.active:
        raise OrderError("Product is not available")

    variant: ProductVariant | None = None
    if variant_id is not None:
        variant = await session.scalar(
            select(ProductVariant)
            .where(ProductVariant.id == variant_id, ProductVariant.product_id == product.id)
            .execution_options(populate_existing=True)
        )
        if variant is None:
            raise OrderNotFoundError("Variant not found")

    existing = next(
        (
            item
            for item in order.items
            if item.product_id == product_id and item.variant_id == variant_id
        ),
        None,
    )
    if existing is not None:
        existing.qty += qty
        await session.commit()
        await session.refresh(existing)
        return existing

    unit_price = (
        variant.price_override
        if variant is not None and variant.price_override is not None
        else product.price
    )
    item = OrderItem(
        order=order,
        product_id=product.id,
        variant_id=variant.id if variant is not None else None,
        name_snapshot=product.name,
        variant_snapshot=(
            {"name": variant.name, "options": variant.options} if variant is not None else None
        ),
        qty=qty,
        unit_price=money(unit_price),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def remove_item(session: AsyncSession, order: Order, item_id: uuid.UUID) -> None:
    if order.status != "draft":
        raise OrderConflictError("Items can only be removed from a draft order")
    item = next((item for item in order.items if item.id == item_id), None)
    if item is None:
        raise OrderNotFoundError("Order item not found")
    await session.delete(item)
    await session.commit()
    await session.refresh(order)


async def set_delivery(
    session: AsyncSession,
    order: Order,
    *,
    zone_id: uuid.UUID,
    address: str,
) -> None:
    if order.status != "draft":
        raise OrderConflictError("Delivery details can only be changed on a draft order")
    address = address.strip()
    if not address:
        raise OrderError("Delivery address is required")
    if len(address) > 500:
        raise OrderError("Delivery address is too long (max 500 characters)")

    zone = await session.scalar(
        select(DeliveryZone)
        .where(DeliveryZone.id == zone_id, DeliveryZone.merchant_id == order.merchant_id)
        .execution_options(populate_existing=True)
    )
    if zone is None:
        raise OrderNotFoundError("Delivery zone not found")

    order.delivery_details = {
        "zone_id": str(zone.id),
        "zone_name": zone.name,
        "fee": str(money(zone.fee)),
        "eta_days": zone.eta_days,
        "address": address,
    }
    await session.commit()
    await session.refresh(order)


async def confirm_order(session: AsyncSession, order: Order) -> Order:
    """Recompute totals from the catalogue and delivery zone, then move to ``confirmed``.

    Catalogue prices are authoritative at confirmation time — snapshots are refreshed so a
    customer can never be charged a stale price.
    """
    if order.status != "draft":
        raise OrderConflictError("Only a draft order can be confirmed")
    if not order.items:
        raise OrderError("Cannot confirm an order with no items")
    if not order.delivery_details:
        raise OrderError("Delivery details are required before confirming")

    subtotal = Decimal("0.00")
    for item in order.items:
        if item.product_id is None:
            raise OrderError(f"Product {item.name_snapshot!r} is no longer available")
        product = await session.get(Product, item.product_id, populate_existing=True)
        if product is None or product.merchant_id != order.merchant_id:
            raise OrderError(f"Product {item.name_snapshot!r} is no longer available")
        if not product.active:
            raise OrderError(f"Product {product.name!r} is no longer available")

        unit_price = product.price
        if item.variant_id is not None:
            variant = await session.get(ProductVariant, item.variant_id, populate_existing=True)
            if variant is None or variant.product_id != product.id:
                raise OrderError(f"Variant for {product.name!r} is no longer available")
            if variant.price_override is not None:
                unit_price = variant.price_override
            item.variant_snapshot = {"name": variant.name, "options": variant.options}
        item.name_snapshot = product.name
        item.unit_price = money(unit_price)
        subtotal += item.unit_price * item.qty

    zone_id = order.delivery_details.get("zone_id")
    try:
        zone_uuid = uuid.UUID(zone_id)
    except (TypeError, ValueError, AttributeError):
        raise OrderError("Delivery details are invalid") from None
    zone = await session.get(DeliveryZone, zone_uuid, populate_existing=True)
    if zone is None or zone.merchant_id != order.merchant_id:
        raise OrderError("Delivery zone is no longer available")

    order.subtotal = money(subtotal)
    order.delivery_fee = money(zone.fee)
    order.total = money(order.subtotal + order.delivery_fee)
    order.delivery_details = {
        **order.delivery_details,
        "zone_name": zone.name,
        "fee": str(order.delivery_fee),
        "eta_days": zone.eta_days,
    }
    _transition(order, "confirmed", trigger="system")
    await session.commit()
    await session.refresh(order)
    return order


async def mark_pending_payment(
    session: AsyncSession,
    order: Order,
    *,
    paypal_order_id: str,
    approval_link: str,
    expires_at: datetime | None = None,
) -> Order:
    """Called by the payments layer once a PayPal order/link has been created."""
    if not order.total or order.total <= 0:
        raise OrderError("Cannot request payment for an order without a total")
    _transition(order, "pending_payment", trigger="system")
    order.paypal_order_id = paypal_order_id
    order.approval_link = approval_link
    order.expires_at = expires_at
    await session.commit()
    await session.refresh(order)
    return order


async def mark_paid(
    session: AsyncSession, order: Order, *, paid_at: datetime | None = None
) -> Order:
    """Webhook-only path. Never expose this through an owner-facing route."""
    _transition(order, "paid", trigger="webhook")
    order.paid_at = paid_at or datetime.now(UTC)
    await session.commit()
    await session.refresh(order)
    return order


async def cancel_order(session: AsyncSession, order: Order) -> Order:
    _transition(order, "cancelled", trigger="owner")
    await session.commit()
    await session.refresh(order)
    return order


async def fulfill_order(session: AsyncSession, order: Order) -> Order:
    _transition(order, "fulfilled", trigger="owner")
    await session.commit()
    await session.refresh(order)
    return order


async def expire_order(session: AsyncSession, order: Order) -> Order:
    """Called by the recovery worker. Never expose this through an owner-facing route."""
    _transition(order, "expired", trigger="worker")
    await session.commit()
    await session.refresh(order)
    return order
