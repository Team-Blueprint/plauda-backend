"""State-gated order tools.

The model can only request order changes through these functions. Every price, stock check,
delivery fee, total, state transition, and payment link is resolved by the existing server-side
order/payment services.
"""

import re
import uuid
from typing import Annotated

from pydantic import Field
from sqlalchemy import select

from app.agent.deps import AgentDeps
from app.agent.order_context import money, summarize_order
from app.db.models import DeliveryZone, Order
from app.orders import service as order_service
from app.orders.errors import OrderError
from app.orders.events import publish_order_update
from app.payments.errors import PaymentError
from app.payments.service import create_payment_link_for_order

_CONFIRMATION_PATTERN = re.compile(
    r"\b(?:yes|yeah|yep|confirm(?:ed|ing|ation)?|proceed|go\s+ahead|"
    r"place\s+(?:the\s+)?order|that(?:'s|\s+is)\s+(?:correct|right)|sounds\s+good)\b",
    re.IGNORECASE,
)


def _buyer_confirmed(deps: AgentDeps) -> bool:
    return bool(_CONFIRMATION_PATTERN.search(deps.current_message))


async def _latest_order(deps: AgentDeps) -> Order | None:
    return await order_service.get_latest_order_for_conversation(
        deps.session,
        deps.merchant.id,
        deps.conversation.id,
    )


def _publish(order: Order) -> None:
    publish_order_update(order)


def _error(exc: Exception) -> str:
    return (
        f"That action could not be completed: {exc}. "
        "Explain briefly to the buyer and offer to connect them with the seller."
    )


def _already_active(order: Order) -> str:
    return (
        f"An order is already in progress (status={order.status}). "
        "Do not start a second order while it is confirmed or waiting for payment. "
        "Share the existing order summary or payment link instead.\n" + summarize_order(order)
    )


async def start_order(deps: AgentDeps) -> str:
    """Start a new draft order for this conversation if there is no active order."""
    latest = await _latest_order(deps)
    if latest is not None:
        if latest.status == "draft":
            return "A draft order already exists.\n" + summarize_order(latest)
        if latest.status in {"confirmed", "pending_payment"}:
            return _already_active(latest)

    order = await order_service.create_draft(
        deps.session,
        merchant_id=deps.merchant.id,
        conversation_id=deps.conversation.id,
        customer_id=deps.conversation.customer_id,
    )
    _publish(order)
    return (
        "Draft order started. Use add_order_item with product and variant ids from "
        "search_catalogue.\n" + summarize_order(order)
    )


async def add_order_item(
    deps: AgentDeps,
    product_id: Annotated[
        uuid.UUID,
        Field(description="Product id returned by search_catalogue."),
    ],
    variant_id: Annotated[
        uuid.UUID | None,
        Field(description="Variant id when the buyer chose a variant; otherwise null."),
    ] = None,
    qty: Annotated[int, Field(description="Quantity to add (1-99).", ge=1, le=99)] = 1,
) -> str:
    """Add a catalogue product to the draft order, creating a draft if needed."""
    latest = await _latest_order(deps)
    if latest is not None and latest.status in {"confirmed", "pending_payment"}:
        return _already_active(latest)

    order = latest if latest is not None and latest.status == "draft" else None
    if order is None:
        order = await order_service.create_draft(
            deps.session,
            merchant_id=deps.merchant.id,
            conversation_id=deps.conversation.id,
            customer_id=deps.conversation.customer_id,
        )

    try:
        item = await order_service.add_item(
            deps.session,
            order,
            product_id=product_id,
            variant_id=variant_id,
            qty=qty,
        )
    except OrderError as exc:
        _publish(order)
        return _error(exc)

    await deps.session.refresh(order)
    _publish(order)
    return (
        f"Added item {item.id}: {item.qty} x {item.name_snapshot} at "
        f"{money(item.unit_price)} {order.currency} each.\n" + summarize_order(order)
    )


async def remove_order_item(
    deps: AgentDeps,
    item_id: Annotated[uuid.UUID, Field(description="Order item id from the order summary.")],
) -> str:
    """Remove one item from the current draft order."""
    order = await _latest_order(deps)
    if order is None:
        return "There is no order to change yet."
    if order.status != "draft":
        return f"Only a draft order can be changed; this order is {order.status}."
    try:
        await order_service.remove_item(deps.session, order, item_id)
    except OrderError as exc:
        return _error(exc)
    await deps.session.refresh(order)
    _publish(order)
    return "Item removed.\n" + summarize_order(order)


async def get_delivery_options(deps: AgentDeps) -> str:
    """List the merchant's delivery zones, fees, areas, and ETAs."""
    zones = list(
        await deps.session.scalars(
            select(DeliveryZone)
            .where(DeliveryZone.merchant_id == deps.merchant.id)
            .order_by(DeliveryZone.name)
        )
    )
    if not zones:
        return (
            "No delivery options are configured for this store. "
            "Offer to connect the buyer with the seller."
        )
    lines = ["Delivery options (server-owned):"]
    for zone in zones:
        areas = ", ".join(str(area) for area in (zone.areas or [])) or "not listed"
        lines.append(
            f"- zone {zone.id}: {zone.name}; areas: {areas}; "
            f"fee: {money(zone.fee)} {deps.merchant.currency}; eta_days: {zone.eta_days}"
        )
    return "\n".join(lines)


async def set_delivery_details(
    deps: AgentDeps,
    zone_id: Annotated[uuid.UUID, Field(description="Delivery zone id from get_delivery_options.")],
    address: Annotated[
        str,
        Field(description="Full delivery address supplied by the buyer.", max_length=500),
    ],
) -> str:
    """Set the delivery zone and address on the current draft order."""
    order = await _latest_order(deps)
    if order is None:
        return "There is no draft order yet. Add an item first or call start_order."
    if order.status != "draft":
        return f"Delivery details cannot be changed on a {order.status} order."
    try:
        await order_service.set_delivery(
            deps.session,
            order,
            zone_id=zone_id,
            address=address,
        )
    except OrderError as exc:
        return _error(exc)
    await deps.session.refresh(order)
    _publish(order)
    return "Delivery details saved.\n" + summarize_order(order)


async def confirm_order(deps: AgentDeps) -> str:
    """Confirm the draft order and recompute all totals from live catalogue and zone data."""
    order = await _latest_order(deps)
    if order is None:
        return "There is no order to confirm yet."
    if order.status in {"confirmed", "pending_payment", "paid"}:
        return (
            f"This order is already {order.status}; do not confirm it again.\n"
            + summarize_order(order)
        )
    if order.status != "draft":
        return f"This order cannot be confirmed because it is {order.status}."
    if not _buyer_confirmed(deps):
        return (
            "The buyer has not explicitly confirmed yet. Present the itemized order, delivery "
            "fee, and server-computed total, then ask them to reply yes. Do not call "
            "confirm_order again until the buyer confirms in a later message.\n"
            + summarize_order(order)
        )
    try:
        order = await order_service.confirm_order(deps.session, order)
    except OrderError as exc:
        return _error(exc)
    _publish(order)
    return (
        "Order confirmed. The server computed the final totals below. "
        "Now ask the buyer to pay using create_payment_link.\n" + summarize_order(order)
    )


async def create_payment_link(deps: AgentDeps) -> str:
    """Create the PayPal approval link for the confirmed order."""
    order = await _latest_order(deps)
    if order is None:
        return "There is no order yet. Build and confirm the order first."
    if order.status == "pending_payment" and order.approval_link:
        return (
            "A payment link already exists; share it once and do not claim payment is confirmed.\n"
            + summarize_order(order)
        )
    if order.status != "confirmed":
        return (
            f"A payment link can only be created for a confirmed order; this order is "
            f"{order.status}. Confirm the order first."
        )
    try:
        order = await create_payment_link_for_order(
            deps.session,
            order,
            trigger="agent",
        )
    except PaymentError as exc:
        return _error(exc)
    return (
        "Payment link created. Give it to the buyer and say payment is only confirmed after "
        "PayPal notifies the store.\n" + summarize_order(order)
    )
