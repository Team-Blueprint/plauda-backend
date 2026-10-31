import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_token
from app.conversations import service
from app.conversations.deps import bearer_token
from app.conversations.schemas import (
    ConversationListOut,
    ConversationOut,
    ConversationStatus,
    MessageListOut,
    MessageOut,
    StaffMessageIn,
)
from app.conversations.sse import MERCHANT_CHANNEL, SSE_HEADERS, stream_events
from app.db.models import Conversation, Order, User
from app.db.session import get_sessionmaker
from app.deps import CurrentUserDep, SessionDep

router = APIRouter(prefix="/conversations", tags=["inbox"])


@router.get(
    "/stream",
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream"}},
    openapi_extra={"security": [{"HTTPBearer": []}]},
)
async def owner_stream(request: Request) -> StreamingResponse:
    token = bearer_token(request)
    payload = decode_token(token)
    try:
        user_id = uuid.UUID(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from None

    # Keep the DB session out of the long-lived stream.
    async with get_sessionmaker()() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        merchant_id = user.merchant_id

    return StreamingResponse(
        stream_events(request, MERCHANT_CHANNEL, merchant_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("", response_model=ConversationListOut)
async def list_conversations(
    user: CurrentUserDep,
    session: SessionDep,
    status_filter: Annotated[ConversationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationListOut:
    conditions = [Conversation.merchant_id == user.merchant_id]
    if status_filter is not None:
        conditions.append(Conversation.status == status_filter)

    total = await session.scalar(select(func.count(Conversation.id)).where(*conditions))
    rows = await session.scalars(
        select(Conversation)
        .where(*conditions)
        .order_by(Conversation.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return ConversationListOut(items=list(rows), total=total or 0, limit=limit, offset=offset)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation_detail(
    conversation_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> ConversationOut:
    conversation = await service.get_conversation(session, user.merchant_id, conversation_id)
    return await _conversation_out(session, conversation)


async def _conversation_out(session: AsyncSession, conversation: Conversation) -> ConversationOut:
    latest_order_id = await session.scalar(
        select(Order.id)
        .where(Order.conversation_id == conversation.id)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    out = ConversationOut.model_validate(conversation)
    out.latest_order_id = latest_order_id
    return out


@router.get("/{conversation_id}/messages", response_model=MessageListOut)
async def inbox_messages(
    conversation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MessageListOut:
    conversation = await service.get_conversation(session, user.merchant_id, conversation_id)
    items, total = await service.list_messages(session, conversation.id, limit=limit, offset=offset)
    return MessageListOut(items=items, total=total, limit=limit, offset=offset)


@router.post("/{conversation_id}/accept", response_model=ConversationOut)
async def accept_conversation(
    conversation_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> ConversationOut:
    conversation = await service.get_conversation(session, user.merchant_id, conversation_id)
    conversation = await service.accept_conversation(session, conversation)
    return await _conversation_out(session, conversation)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def staff_reply(
    conversation_id: uuid.UUID,
    payload: StaffMessageIn,
    user: CurrentUserDep,
    session: SessionDep,
) -> MessageOut:
    conversation = await service.get_conversation(session, user.merchant_id, conversation_id)
    message = await service.add_staff_message(session, conversation, payload.content)
    return MessageOut.model_validate(message)


@router.post("/{conversation_id}/return-to-ai", response_model=ConversationOut)
async def return_to_ai(
    conversation_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> ConversationOut:
    conversation = await service.get_conversation(session, user.merchant_id, conversation_id)
    conversation = await service.return_to_ai(session, conversation)
    return await _conversation_out(session, conversation)


@router.post("/{conversation_id}/close", response_model=ConversationOut)
async def close_conversation(
    conversation_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> ConversationOut:
    conversation = await service.get_conversation(session, user.merchant_id, conversation_id)
    conversation = await service.close_conversation(session, conversation)
    return await _conversation_out(session, conversation)
