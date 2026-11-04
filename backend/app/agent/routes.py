from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.agent.agent import AgentConfigError, get_agent_model
from app.agent.schemas import ChatTurnIn
from app.agent.service import stream_turn
from app.conversations import service as conversation_service
from app.conversations.deps import bearer_token
from app.conversations.sse import SSE_HEADERS, sse_frame
from app.conversations.tokens import token_matches
from app.db.models import Conversation, Merchant
from app.deps import SessionDep

router = APIRouter(prefix="/public", tags=["public-chat"])


async def _sse_events(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for event in events:
        yield sse_frame(event)


@router.post(
    "/chat/{slug}/messages",
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Agent turn SSE stream"},
        503: {"description": "AI assistant is not configured"},
    },
    openapi_extra={"security": [{"HTTPBearer": []}]},
)
async def public_chat_turn(
    slug: str,
    payload: ChatTurnIn,
    request: Request,
    session: SessionDep,
) -> StreamingResponse:
    """Persist a buyer message and stream one assistant turn over SSE."""
    merchant = await session.scalar(select(Merchant).where(Merchant.slug == slug))
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")

    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.merchant_id == merchant.id,
        )
    )
    if conversation is None or not token_matches(
        bearer_token(request), conversation.visitor_token_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    if conversation.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation is closed",
        )

    model = None
    if conversation.status == "ai":
        try:
            model = get_agent_model()
        except AgentConfigError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The AI assistant is not configured",
            ) from exc

    message = await conversation_service.add_customer_message(
        session,
        conversation,
        payload.content,
    )

    if model is None:

        async def human_events() -> AsyncIterator[str]:
            yield sse_frame(
                {
                    "type": "system",
                    "kind": "handoff",
                    "text": f"A person from {merchant.name} will reply here.",
                }
            )
            yield sse_frame({"type": "done"})

        return StreamingResponse(
            human_events(),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return StreamingResponse(
        _sse_events(
            stream_turn(
                session,
                conversation,
                merchant,
                payload.content,
                model=model,
                current_message_id=message.id,
            )
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
