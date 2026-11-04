from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.agent.agent import AgentConfigError, get_agent_model
from app.agent.handoff import classify_handoff, detect_handoff_request
from app.agent.rate_limit import RateLimitCheck, chat_turn_limiter
from app.agent.schemas import ChatTurnIn
from app.agent.service import stream_turn
from app.config import get_settings
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


async def _handoff_events(merchant: Merchant) -> AsyncIterator[str]:
    yield sse_frame(
        {
            "type": "system",
            "kind": "handoff",
            "text": f"A person from {merchant.name} will reply here.",
        }
    )
    yield sse_frame({"type": "done"})


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client is not None else "unknown"


def _enforce_rate_limit(request: Request, conversation: Conversation) -> None:
    settings = get_settings()
    result = chat_turn_limiter.consume(
        [
            RateLimitCheck(
                scope="ip",
                key=_client_ip(request),
                limit=settings.chat_rate_limit_per_ip,
            ),
            RateLimitCheck(
                scope="conversation",
                key=str(conversation.id),
                limit=settings.chat_rate_limit_per_conversation,
            ),
        ],
        window_seconds=settings.chat_rate_limit_window_seconds,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many messages. Please wait a moment and try again.",
            headers={"Retry-After": str(result.retry_after)},
        )


@router.post(
    "/chat/{slug}/messages",
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Agent turn SSE stream"},
        429: {"description": "Rate limit exceeded"},
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

    _enforce_rate_limit(request, conversation)

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
        return StreamingResponse(
            _handoff_events(merchant),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    settings = get_settings()
    handoff_reason = detect_handoff_request(payload.content)
    if handoff_reason is None and settings.handoff_classifier_enabled:
        decision = await classify_handoff(payload.content)
        if decision.should_handoff:
            handoff_reason = decision.reason.strip() or "The buyer needs a human"

    if handoff_reason is not None:
        await conversation_service.request_handoff(
            session,
            conversation,
            reason=handoff_reason[:500],
        )
        return StreamingResponse(
            _handoff_events(merchant),
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
