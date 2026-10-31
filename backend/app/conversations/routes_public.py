import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.conversations import service
from app.conversations.deps import VisitorConversationDep, bearer_token
from app.conversations.schemas import (
    ConversationCreate,
    ConversationCreatedOut,
    ConversationOut,
    HandoffIn,
    MessageListOut,
)
from app.conversations.sse import CONVERSATION_CHANNEL, SSE_HEADERS, stream_events
from app.conversations.tokens import token_matches
from app.db.models import Conversation, Merchant
from app.db.session import get_sessionmaker
from app.deps import SessionDep

router = APIRouter(prefix="/public", tags=["public-chat"])


@router.post(
    "/chat/{slug}/conversations",
    response_model=ConversationCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    slug: str,
    session: SessionDep,
    payload: ConversationCreate | None = None,
) -> ConversationCreatedOut:
    merchant = await session.scalar(select(Merchant).where(Merchant.slug == slug))
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")

    conversation, visitor_token = await service.create_conversation(
        session,
        merchant,
        name=payload.name if payload else None,
        contact=payload.contact if payload else None,
    )
    return ConversationCreatedOut(
        conversation_id=conversation.id,
        visitor_token=visitor_token,
        status=conversation.status,
        started_at=conversation.started_at,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListOut)
async def public_messages(
    conversation: VisitorConversationDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MessageListOut:
    items, total = await service.list_messages(session, conversation.id, limit=limit, offset=offset)
    return MessageListOut(items=items, total=total, limit=limit, offset=offset)


@router.post("/conversations/{conversation_id}/handoff", response_model=ConversationOut)
async def public_handoff(
    conversation: VisitorConversationDep,
    session: SessionDep,
    payload: HandoffIn | None = None,
) -> ConversationOut:
    conversation = await service.request_handoff(
        session, conversation, reason=payload.reason if payload else None
    )
    return ConversationOut.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/stream",
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream"}},
    openapi_extra={"security": [{"HTTPBearer": []}]},
)
async def public_stream(conversation_id: uuid.UUID, request: Request) -> StreamingResponse:
    token = bearer_token(request)
    # Keep the DB session out of the long-lived stream.
    async with get_sessionmaker()() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        if conversation is None or not token_matches(token, conversation.visitor_token_hash):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
            )
    return StreamingResponse(
        stream_events(request, CONVERSATION_CHANNEL, conversation_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
