"""Publish order-card changes to the live chat and owner inbox streams."""

from app.conversations.sse import CONVERSATION_CHANNEL, MERCHANT_CHANNEL, hub
from app.db.models import Order
from app.orders.cards import order_card


def publish_order_update(order: Order) -> None:
    payload = {"type": "order_update", "order": order_card(order)}
    if order.conversation_id is not None:
        hub.publish(CONVERSATION_CHANNEL, order.conversation_id, payload)
    hub.publish(MERCHANT_CHANNEL, order.merchant_id, payload)
