from app.agent.deps import AgentDeps
from app.rag.embedders.base import EmbeddingError
from app.rag.retrieval import search_business_info


async def search_store_info(deps: AgentDeps, query: str, limit: int = 8) -> str:
    """Return approved store text with source labels, or an honest no-result message."""
    query = query.strip()
    if not query:
        return "No store information question was provided."

    try:
        chunks = await search_business_info(
            deps.session,
            deps.merchant.id,
            query,
            provider=deps.embedding_provider,
            vector_limit=min(max(limit, 1), 10),
            text_limit=min(max(limit, 1), 10),
        )
    except EmbeddingError:
        return (
            "The store knowledge index is temporarily unavailable. "
            "Tell the buyer you will check with the seller."
        )

    if not chunks:
        return "No approved store information matched that question."

    return "\n\n".join(
        f"[{index}] ({chunk.source}) {chunk.content}" for index, chunk in enumerate(chunks, start=1)
    )
