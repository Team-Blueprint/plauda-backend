import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeChunk
from app.rag.embedders.base import EmbeddingError, EmbeddingProvider, validate_embeddings
from app.rag.embedders.factory import EMBEDDING_DIMS, get_embedding_provider

HYBRID_VECTOR_WEIGHT = 0.7
HYBRID_TEXT_WEIGHT = 0.3


@dataclass(frozen=True)
class RetrievedChunk:
    id: uuid.UUID
    source: str
    content: str
    score: float


async def search_business_info(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    query: str,
    *,
    provider: EmbeddingProvider | None = None,
    vector_limit: int = 8,
    text_limit: int = 5,
) -> list[RetrievedChunk]:
    """Search one merchant's indexed business info using hybrid ranking."""
    if not query.strip():
        return []
    if vector_limit <= 0 or text_limit <= 0:
        raise ValueError("vector_limit and text_limit must be greater than zero")

    provider = provider or get_embedding_provider()
    if provider.dims != EMBEDDING_DIMS:
        raise EmbeddingError(
            f"{provider.name} produces {provider.dims}-dimensional vectors; "
            f"the index requires {EMBEDDING_DIMS}"
        )

    query_vector = validate_embeddings(
        await provider.embed([query]),
        expected_count=1,
        dims=EMBEDDING_DIMS,
        provider=provider.name,
    )[0]

    vector_distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
    vector_matches = (
        select(
            KnowledgeChunk.id.label("id"),
            (1 - vector_distance).label("score"),
        )
        .where(KnowledgeChunk.merchant_id == merchant_id)
        .order_by(vector_distance)
        .limit(vector_limit)
        .cte("vector_matches")
    )

    tsquery = func.websearch_to_tsquery("simple", query)
    text_rank = func.ts_rank_cd(KnowledgeChunk.tsv, tsquery)
    text_matches = (
        select(
            KnowledgeChunk.id.label("id"),
            text_rank.label("score"),
        )
        .where(
            KnowledgeChunk.merchant_id == merchant_id,
            KnowledgeChunk.tsv.op("@@")(tsquery),
        )
        .order_by(text_rank.desc())
        .limit(text_limit)
        .cte("text_matches")
    )

    score = (
        HYBRID_VECTOR_WEIGHT * func.coalesce(vector_matches.c.score, 0.0)
        + HYBRID_TEXT_WEIGHT * func.coalesce(text_matches.c.score, 0.0)
    ).label("score")

    statement = (
        select(
            KnowledgeChunk.id,
            KnowledgeChunk.source,
            KnowledgeChunk.content,
            score,
        )
        .outerjoin(vector_matches, KnowledgeChunk.id == vector_matches.c.id)
        .outerjoin(text_matches, KnowledgeChunk.id == text_matches.c.id)
        .where(
            KnowledgeChunk.merchant_id == merchant_id,
            or_(
                vector_matches.c.id.is_not(None),
                text_matches.c.id.is_not(None),
            ),
        )
        .order_by(score.desc(), KnowledgeChunk.chunk_index)
    )

    rows = (await session.execute(statement)).all()
    return [
        RetrievedChunk(
            id=row.id,
            source=row.source,
            content=row.content,
            score=float(row.score),
        )
        for row in rows
    ]
