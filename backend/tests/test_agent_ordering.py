import json
import uuid
from decimal import Decimal

from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from sqlalchemy import select

from app.agent.deps import AgentDeps
from app.agent.service import stream_turn
from app.agent.tools.orders import (
    add_order_item,
    confirm_order,
    create_payment_link,
    get_delivery_options,
    remove_order_item,
    set_delivery_details,
    start_order,
)
from app.conversations import service as conversation_service
from app.db.models import (
    Conversation,
    DeliveryZone,
    Merchant,
    Message,
    Order,
    Product,
    ProductVariant,
)
from app.orders.cards import order_card


async def _conversation(session, merchant_id: uuid.UUID) -> Conversation:
    merchant = await session.get(Merchant, merchant_id)
    conversation, _ = await conversation_service.create_conversation(session, merchant)
    return conversation


def _deps(session, merchant, conversation) -> AgentDeps:
    return AgentDeps(
        session,
        merchant,
        conversation,
        current_message="Yes, please confirm the order.",
    )


async def _seed_catalogue(session, merchant_id: uuid.UUID, *, stock: int = 4):
    product = Product(
        merchant_id=merchant_id,
        name="Silk scarf",
        description="Hand-dyed",
        price=Decimal("25.00"),
        currency="USD",
    )
    variant = ProductVariant(
        product=product,
        name="Red",
        options={"color": "red"},
        price_override=Decimal("30.00"),
        stock=stock,
    )
    zone = DeliveryZone(
        merchant_id=merchant_id,
        name="Island",
        areas=["Yaba"],
        fee=Decimal("5.50"),
        eta_days=2,
    )
    session.add_all([product, variant, zone])
    await session.commit()
    await session.refresh(product)
    await session.refresh(variant)
    await session.refresh(zone)
    return product, variant, zone


class FakePayPalClient:
    def __init__(self) -> None:
        self.calls = 0
        self.kwargs: dict | None = None

    async def create_order(self, **kwargs) -> dict:
        self.calls += 1
        self.kwargs = kwargs
        return {
            "id": "PAYPAL-AGENT-1",
            "links": [{"rel": "approve", "href": "https://paypal.example/approve-agent"}],
        }


async def test_order_tools_build_confirm_and_create_payment_link(
    db_session, merchant_auth, monkeypatch
):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)
    product, variant, zone = await _seed_catalogue(db_session, merchant_id)
    deps = _deps(db_session, merchant, conversation)

    started = await start_order(deps)
    assert "Draft order started" in started

    added = await add_order_item(deps, product.id, variant.id, 2)
    assert "Added item" in added
    assert "30.00 USD" in added

    options = await get_delivery_options(deps)
    assert "Island" in options
    assert "5.50 USD" in options
    assert str(zone.id) in options

    delivery = await set_delivery_details(deps, zone.id, "12 Allen Avenue")
    assert "Delivery details saved" in delivery
    assert "12 Allen Avenue" in delivery

    confirmed = await confirm_order(deps)
    assert "Order confirmed" in confirmed
    assert "Total: 65.50 USD" in confirmed

    fake = FakePayPalClient()
    monkeypatch.setattr("app.payments.service.client_for_merchant", lambda merchant: fake)
    linked = await create_payment_link(deps)
    assert "Payment link created" in linked
    assert "https://paypal.example/approve-agent" in linked
    assert fake.calls == 1
    assert fake.kwargs is not None
    assert fake.kwargs["amount"] == Decimal("65.50")
    assert fake.kwargs["currency"] == "USD"

    order = await db_session.scalar(select(Order).where(Order.conversation_id == conversation.id))
    assert order is not None
    assert order.status == "pending_payment"
    assert order.paypal_order_id == "PAYPAL-AGENT-1"
    assert order.customer_id == conversation.customer_id
    assert order.subtotal == Decimal("60.00")
    assert order.delivery_fee == Decimal("5.50")
    assert order.total == Decimal("65.50")
    assert order.items[0].qty == 2

    card = order_card(order)
    assert card["id"] == str(order.id)
    assert card["currency"] == "USD"
    assert card["items"][0]["name"] == "Silk scarf"
    assert card["items"][0]["unit_price"] == "30.00"
    assert card["subtotal"] == "60.00"
    assert card["total"] == "65.50"
    assert card["approval_link"] == "https://paypal.example/approve-agent"


async def test_confirm_requires_explicit_buyer_confirmation(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)
    product, variant, zone = await _seed_catalogue(db_session, merchant_id)
    deps = AgentDeps(
        db_session,
        merchant,
        conversation,
        current_message="Please deliver it to 12 Allen Avenue in Yaba.",
    )

    await start_order(deps)
    await add_order_item(deps, product.id, variant.id, 1)
    await set_delivery_details(deps, zone.id, "12 Allen Avenue")

    blocked = await confirm_order(deps)
    assert "not explicitly confirmed" in blocked
    deps.current_message = "I'm not sure yet."
    blocked_again = await confirm_order(deps)
    assert "not explicitly confirmed" in blocked_again
    order = await db_session.scalar(select(Order).where(Order.conversation_id == conversation.id))
    assert order is not None
    assert order.status == "draft"

    deps.current_message = "Yes, that is correct — please confirm."
    confirmed = await confirm_order(deps)
    assert "Order confirmed" in confirmed
    await db_session.refresh(order)
    assert order.status == "confirmed"


async def test_payment_link_is_blocked_before_confirmation(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)
    product, _, _ = await _seed_catalogue(db_session, merchant_id)
    deps = _deps(db_session, merchant, conversation)

    await start_order(deps)
    await add_order_item(deps, product.id, None, 1)
    result = await create_payment_link(deps)
    assert "confirmed" in result

    order = await db_session.scalar(select(Order).where(Order.conversation_id == conversation.id))
    assert order is not None
    assert order.status == "draft"
    assert order.approval_link is None


async def test_order_tools_enforce_stock_and_tenant_scope(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)
    product, variant, zone = await _seed_catalogue(db_session, merchant_id, stock=1)
    deps = _deps(db_session, merchant, conversation)

    await start_order(deps)
    too_many = await add_order_item(deps, product.id, variant.id, 2)
    assert "in stock" in too_many
    missing_variant = await add_order_item(deps, product.id, None, 1)
    assert "Choose a variant" in missing_variant
    order = await db_session.scalar(select(Order).where(Order.conversation_id == conversation.id))
    assert order is not None
    assert order.items == []

    other = Merchant(name="Other", slug=f"pytest-other-{uuid.uuid4().hex[:8]}")
    db_session.add(other)
    await db_session.flush()
    other_product = Product(
        merchant_id=other.id,
        name="Other scarf",
        price=Decimal("10.00"),
        currency="USD",
    )
    other_zone = DeliveryZone(
        merchant_id=other.id,
        name="Other zone",
        areas=["Elsewhere"],
        fee=Decimal("2.00"),
    )
    db_session.add_all([other_product, other_zone])
    await db_session.commit()

    foreign_product = await add_order_item(deps, other_product.id, None, 1)
    assert "not found" in foreign_product.lower()
    foreign_zone = await set_delivery_details(deps, other_zone.id, "1 Other Street")
    assert "not found" in foreign_zone.lower()

    available = await add_order_item(deps, product.id, variant.id, 1)
    assert "Added item" in available
    foreign_item = await remove_order_item(deps, uuid.uuid4())
    assert "not found" in foreign_item.lower()


async def test_stream_turn_emits_order_update_after_order_tool(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)
    product, variant, _ = await _seed_catalogue(db_session, merchant_id)
    customer_message = await conversation_service.add_customer_message(
        db_session, conversation, "Add one scarf"
    )

    async def model_stream(messages, info):
        has_tool_return = any(
            isinstance(part, ToolReturnPart) for message in messages for part in message.parts
        )
        if not has_tool_return:
            yield {
                0: DeltaToolCall(
                    "add_order_item",
                    json_args=json.dumps(
                        {
                            "product_id": str(product.id),
                            "variant_id": str(variant.id),
                            "qty": 1,
                        }
                    ),
                    tool_call_id="call-add-item",
                )
            }
        else:
            yield "Added it."

    events = [
        event
        async for event in stream_turn(
            db_session,
            conversation,
            merchant,
            "Add one scarf",
            model=FunctionModel(stream_function=model_stream),
            current_message_id=customer_message.id,
        )
    ]

    order_events = [event for event in events if event["type"] == "order_update"]
    assert len(order_events) == 1
    assert order_events[0]["order"]["status"] == "draft"
    assert order_events[0]["order"]["items"][0]["name"] == "Silk scarf"
    assert order_events[0]["order"]["subtotal"] is None
    assert events[-1] == {"type": "done"}

    order = await db_session.scalar(select(Order).where(Order.conversation_id == conversation.id))
    assert order is not None
    messages = list(
        await db_session.scalars(select(Message).where(Message.conversation_id == conversation.id))
    )
    assert any(message.role == "agent" and message.content == "Added it." for message in messages)
