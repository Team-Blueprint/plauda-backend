import uuid
from decimal import Decimal

from sqlalchemy import select

from app.agent.deps import AgentDeps
from app.agent.tools.business_info import search_store_info
from app.agent.tools.catalogue import search_products
from app.agent.tools.handoff import request_human_handoff
from app.db.models import Conversation, Merchant, Message, Product, ProductVariant


class FakeEmbeddingProvider:
    name = "fake"
    model = "fake-1024"
    dims = 1024

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]


async def _conversation(session, merchant_id: uuid.UUID) -> Conversation:
    conversation = Conversation(
        merchant_id=merchant_id,
        status="ai",
        visitor_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def test_catalogue_tool_returns_exact_price_and_stays_tenant_scoped(
    db_session, merchant_auth
):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)

    product = Product(
        merchant_id=merchant_id,
        name="Silk scarf",
        description="Hand-dyed",
        price=Decimal("25.00"),
        currency="USD",
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ProductVariant(
            product_id=product.id,
            name="Red",
            price_override=Decimal("30.00"),
            stock=4,
        )
    )

    other = Merchant(name="Other", slug=f"pytest-other-{uuid.uuid4().hex[:8]}")
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        Product(
            merchant_id=other.id,
            name="Silk scarf from another store",
            price=Decimal("99.00"),
            currency="USD",
        )
    )
    await db_session.commit()

    result = await search_products(
        AgentDeps(db_session, merchant, conversation),
        "scarf",
    )

    assert "Silk scarf" in result
    assert "25.00 USD" in result
    assert "Red" in result
    assert "30.00 USD" in result
    assert "stock=4" in result
    assert "another store" not in result


async def test_business_info_tool_handles_empty_corpus(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)

    result = await search_store_info(
        AgentDeps(
            db_session,
            merchant,
            conversation,
            embedding_provider=FakeEmbeddingProvider(),
        ),
        "refund policy",
    )

    assert result == "No approved store information matched that question."


async def test_handoff_tool_updates_conversation_and_adds_system_message(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)

    result = await request_human_handoff(
        AgentDeps(db_session, merchant, conversation),
        "Buyer asked for a person",
    )

    assert "handoff was requested" in result
    assert conversation.status == "handoff_requested"
    messages = list(
        await db_session.scalars(select(Message).where(Message.conversation_id == conversation.id))
    )
    assert any(
        message.role == "system" and message.meta["kind"] == "handoff" for message in messages
    )
