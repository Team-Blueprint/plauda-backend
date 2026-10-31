import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.errors import (
    ConversationConflictError,
    ConversationNotFoundError,
)
from app.conversations.schemas import ConversationSummaryOut, MessageOut
from app.conversations.sse import CONVERSATION_CHANNEL, MERCHANT_CHANNEL, hub
from app.conversations.state_machine import ConversationStateError, ensure_transition
from app.conversations.tokens import new_visitor_token
from app.db.models import Conversation, Customer, Merchant, Message


async def get_conversation(
    session: AsyncSession, merchant_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.merchant_id == merchant_id
        )
    )
    if conversation is None:
        raise ConversationNotFoundError("Conversation not found")
    return conversation


async def create_conversation(
    session: AsyncSession,
    merchant: Merchant,
    *,
    name: str | None = None,
    contact: str | None = None,
) -> tuple[Conversation, str]:
    customer = Customer(merchant_id=merchant.id, name=name, contact=contact)
    token, token_hash = new_visitor_token()
    conversation = Conversation(
        merchant_id=merchant.id,
        customer=customer,
        visitor_token_hash=token_hash,
        status="ai",
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation, token


async def list_messages(
    session: AsyncSession, conversation_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Message], int]:
    total = await session.scalar(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    )
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0


async def add_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    role: str,
    content: str,
    meta: dict | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role=role,
        content=content,
        meta=meta or {},
    )
    conversation.last_message_at = datetime.now(UTC)
    session.add(message)
    await session.commit()
    await session.refresh(message)

    payload = {
        "type": "message",
        "conversation_id": str(conversation.id),
        "message": MessageOut.model_validate(message).model_dump(mode="json"),
    }
    hub.publish(CONVERSATION_CHANNEL, conversation.id, payload)
    hub.publish(MERCHANT_CHANNEL, conversation.merchant_id, payload)
    return message


def _transition(conversation: Conversation, new: str) -> None:
    try:
        ensure_transition(conversation.status, new)
    except ConversationStateError as exc:
        raise ConversationConflictError(str(exc)) from exc
    conversation.status = new


def _publish_status(conversation: Conversation) -> None:
    payload = {
        "type": "conversation_update",
        "conversation": ConversationSummaryOut.model_validate(conversation).model_dump(mode="json"),
    }
    hub.publish(CONVERSATION_CHANNEL, conversation.id, payload)
    hub.publish(MERCHANT_CHANNEL, conversation.merchant_id, payload)


async def request_handoff(
    session: AsyncSession, conversation: Conversation, *, reason: str | None = None
) -> Conversation:
    if conversation.status == "closed":
        raise ConversationConflictError("Conversation is closed")
    if conversation.status == "human_active":
        return conversation

    if conversation.status == "ai":
        _transition(conversation, "handoff_requested")
        changed = True
    else:
        changed = False
    if reason is not None:
        conversation.handoff_reason = reason.strip()[:500] or None

    await session.commit()
    await session.refresh(conversation)
    if changed:
        await add_message(
            session,
            conversation,
            role="system",
            content="A human has been requested.",
            meta={"kind": "handoff"},
        )
    _publish_status(conversation)
    return conversation


async def accept_conversation(session: AsyncSession, conversation: Conversation) -> Conversation:
    if conversation.status != "handoff_requested":
        raise ConversationConflictError("Only a requested handoff can be accepted")
    _transition(conversation, "human_active")
    await session.commit()
    await session.refresh(conversation)
    await add_message(
        session,
        conversation,
        role="system",
        content="The owner joined the chat.",
        meta={"kind": "handoff"},
    )
    _publish_status(conversation)
    return conversation


async def return_to_ai(session: AsyncSession, conversation: Conversation) -> Conversation:
    if conversation.status != "human_active":
        raise ConversationConflictError("Only an active human conversation can return to AI")
    _transition(conversation, "ai")
    await session.commit()
    await session.refresh(conversation)
    await add_message(
        session,
        conversation,
        role="system",
        content="The conversation returned to the AI assistant.",
        meta={"kind": "handoff"},
    )
    _publish_status(conversation)
    return conversation


async def close_conversation(session: AsyncSession, conversation: Conversation) -> Conversation:
    if conversation.status == "closed":
        raise ConversationConflictError("Conversation is already closed")
    _transition(conversation, "closed")
    await session.commit()
    await session.refresh(conversation)
    await add_message(
        session,
        conversation,
        role="system",
        content="The conversation was closed.",
        meta={"kind": "handoff"},
    )
    _publish_status(conversation)
    return conversation


async def add_staff_message(
    session: AsyncSession, conversation: Conversation, content: str
) -> Message:
    if conversation.status != "human_active":
        raise ConversationConflictError(
            "The owner can only reply while the conversation is human_active"
        )
    return await add_message(session, conversation, role="staff", content=content)
