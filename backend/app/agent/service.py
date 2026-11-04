import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.run import AgentRunResultEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import build_agent, get_agent_model
from app.agent.deps import AgentDeps
from app.agent.prompts import build_user_prompt
from app.conversations import service as conversation_service
from app.db.models import Conversation, Merchant, Message
from app.orders import service as order_service
from app.orders.cards import order_card
from app.rag.embedders.base import EmbeddingProvider

logger = logging.getLogger(__name__)

TOOL_LABELS = {
    "search_business_info": "checking the store information",
    "search_catalogue": "checking the catalogue",
    "start_order": "starting the order",
    "add_order_item": "adding to the order",
    "remove_order_item": "updating the order",
    "get_delivery_options": "checking delivery options",
    "set_delivery_details": "saving delivery details",
    "confirm_order": "confirming the order",
    "create_payment_link": "creating the payment link",
    "request_handoff": "connecting you to the seller",
}
ORDER_TOOLS = frozenset(
    {
        "start_order",
        "add_order_item",
        "remove_order_item",
        "set_delivery_details",
        "confirm_order",
        "create_payment_link",
    }
)
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 4000


async def _load_history(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    *,
    exclude_message_id: uuid.UUID | None = None,
) -> list[ModelRequest | ModelResponse]:
    statement = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role.in_(("customer", "agent")),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(MAX_HISTORY_MESSAGES)
    )
    if exclude_message_id is not None:
        statement = statement.where(Message.id != exclude_message_id)

    rows = list(await session.scalars(statement))
    rows.reverse()

    history: list[ModelRequest | ModelResponse] = []
    for message in rows:
        content = message.content.strip()[:MAX_HISTORY_CHARS]
        if not content:
            continue
        if message.role == "customer":
            history.append(ModelRequest(parts=[UserPromptPart(content=build_user_prompt(content))]))
        elif message.role == "agent":
            history.append(ModelResponse(parts=[TextPart(content=content)]))
    return history


async def stream_turn(
    session: AsyncSession,
    conversation: Conversation,
    merchant: Merchant,
    user_text: str,
    *,
    model: Model | None = None,
    current_message_id: uuid.UUID | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run one streamed agent turn and persist the final assistant message."""
    model = model or get_agent_model()
    latest_order = await order_service.get_latest_order_for_conversation(
        session,
        merchant.id,
        conversation.id,
    )
    agent = build_agent(model, merchant, latest_order)
    history = await _load_history(
        session,
        conversation.id,
        exclude_message_id=current_message_id,
    )
    deps = AgentDeps(
        session=session,
        merchant=merchant,
        conversation=conversation,
        embedding_provider=embedding_provider,
        current_message=user_text,
    )

    chunks: list[str] = []
    final_output: str | None = None
    try:
        async with agent.run_stream_events(
            build_user_prompt(user_text),
            deps=deps,
            message_history=history,
        ) as events:
            async for event in events:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    text = event.delta.content_delta
                    if text:
                        chunks.append(text)
                        yield {"type": "delta", "text": text}
                elif isinstance(event, FunctionToolCallEvent):
                    tool = event.part.tool_name
                    yield {
                        "type": "tool_status",
                        "tool": tool,
                        "state": "started",
                        "label": TOOL_LABELS.get(tool, "working"),
                    }
                elif isinstance(event, FunctionToolResultEvent):
                    tool = event.part.tool_name
                    yield {
                        "type": "tool_status",
                        "tool": tool,
                        "state": "done",
                        "label": TOOL_LABELS.get(tool, "done"),
                    }
                    if tool in ORDER_TOOLS:
                        order = await order_service.get_latest_order_for_conversation(
                            session,
                            merchant.id,
                            conversation.id,
                        )
                        if order is not None:
                            yield {"type": "order_update", "order": order_card(order)}
                elif isinstance(event, AgentRunResultEvent):
                    final_output = str(event.result.output)

        text = (final_output or "").strip() or "".join(chunks).strip()
        if not text:
            text = "I'm sorry, I couldn't generate a reply just now. Please try again."
        await conversation_service.add_message(
            session,
            conversation,
            role="agent",
            content=text,
            meta={"kind": "chat"},
        )
        yield {"type": "done"}
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("agent turn failed for conversation %s", conversation.id)
        yield {
            "type": "error",
            "code": "internal",
            "message": "The assistant hit a problem. Please try again.",
        }
        yield {"type": "done"}
