import uuid

from pydantic_ai.models.test import TestModel
from sqlalchemy import select

from app.agent.service import stream_turn
from app.conversations import service as conversation_service
from app.db.models import Conversation, Merchant, Message


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


async def test_stream_turn_emits_deltas_and_persists_agent_message(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    merchant = await db_session.get(Merchant, merchant_id)
    conversation = await _conversation(db_session, merchant_id)
    customer_message = await conversation_service.add_customer_message(
        db_session, conversation, "Do you deliver on Sundays?"
    )

    events = [
        event
        async for event in stream_turn(
            db_session,
            conversation,
            merchant,
            "Do you deliver on Sundays?",
            model=TestModel(call_tools=[], custom_output_text="Yes, we deliver on Sundays."),
            current_message_id=customer_message.id,
        )
    ]

    assert any(event["type"] == "delta" for event in events)
    assert events[-1] == {"type": "done"}

    messages = list(
        await db_session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.id)
        )
    )
    assert [message.role for message in messages] == ["customer", "agent"]
    assert messages[-1].content == "Yes, we deliver on Sundays."
    assert messages[-1].meta["kind"] == "chat"
