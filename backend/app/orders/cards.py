"""Serialization for the live order card contract used by chat SSE."""

from decimal import Decimal
from typing import Any

from app.db.models import Order


def _money(value: Decimal | None) -> str | None:
    return f"{value:.2f}" if value is not None else None


def order_card(order: Order) -> dict[str, Any]:
    """Return the full replacement card for one order.

    Clients replace the previous card with this object rather than merging fields. Money values
    are decimal strings so the browser never performs currency arithmetic.
    """
    return {
        "id": str(order.id),
        "status": order.status,
        "currency": order.currency,
        "items": [
            {
                "product_id": str(item.product_id) if item.product_id else None,
                "variant_id": str(item.variant_id) if item.variant_id else None,
                "name": item.name_snapshot,
                "variant": item.variant_snapshot,
                "qty": item.qty,
                "unit_price": _money(item.unit_price),
            }
            for item in order.items
        ],
        "subtotal": _money(order.subtotal),
        "delivery_fee": _money(order.delivery_fee),
        "total": _money(order.total),
        "delivery_details": order.delivery_details,
        "approval_link": order.approval_link,
    }
