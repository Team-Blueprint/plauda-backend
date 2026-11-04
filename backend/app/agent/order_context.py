"""Human-readable order state shared by prompts and agent tools."""

from decimal import Decimal

from app.db.models import Order


def money(value: Decimal | None) -> str:
    return f"{value:.2f}" if value is not None else "not set"


def variant_label(item) -> str:
    snapshot = item.variant_snapshot or {}
    name = snapshot.get("name")
    return f" ({name})" if name else ""


def summarize_order(order: Order) -> str:
    if not order.items:
        items = "- no items yet"
    else:
        items = "\n".join(
            f"- item {item.id}: {item.qty} x {item.name_snapshot}{variant_label(item)} at "
            f"{money(item.unit_price)} {order.currency} each"
            for item in order.items
        )

    delivery = order.delivery_details or {}
    delivery_text = "not set"
    if delivery:
        delivery_fee = order.delivery_fee
        if delivery_fee is None and delivery.get("fee") is not None:
            delivery_fee = Decimal(str(delivery["fee"]))
        delivery_text = (
            f"{delivery.get('zone_name', 'zone')} to {delivery.get('address', 'address')} "
            f"({money(delivery_fee)} {order.currency}, ETA "
            f"{delivery.get('eta_days', '?')} days)"
        )

    lines = [
        f"Order {order.id} ({order.status}) in {order.currency}:",
        items,
        f"Subtotal: {money(order.subtotal)} {order.currency}",
        f"Delivery: {delivery_text}",
        f"Total: {money(order.total)} {order.currency}",
    ]
    if order.approval_link:
        lines.append(f"Payment link: {order.approval_link}")
    return "\n".join(lines)


def format_order_for_prompt(order: Order | None) -> str:
    if order is None:
        return "Current server-owned order state: no order exists yet."
    return "Current server-owned order state (authoritative):\n" + summarize_order(order)
