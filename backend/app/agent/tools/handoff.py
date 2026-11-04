from app.agent.deps import AgentDeps
from app.conversations import service as conversation_service


async def request_human_handoff(deps: AgentDeps, reason: str) -> str:
    """Move the conversation to the owner inbox and stop the AI from answering."""
    await conversation_service.request_handoff(
        deps.session,
        deps.conversation,
        reason=reason.strip()[:500] or "Buyer asked for a human",
    )
    return "A human handoff was requested. Tell the buyer a person from the store will take over."
