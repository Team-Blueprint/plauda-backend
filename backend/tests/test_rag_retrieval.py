import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessInfoDocument, KnowledgeChunk, Merchant
from app.rag.retrieval import HYBRID_TEXT_WEIGHT, HYBRID_VECTOR_WEIGHT, search_business_info

VECTOR_NEAR = [1.0] + [0.0] * 1023
VECTOR_FAR = [0.0, 1.0] + [0.0] * 1022


class QueryEmbeddingProvider:
    name = "fake"
    model = "fake-1024"
    dims = 1024

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vector for _ in texts]


async def _seed_chunk(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    *,
    source: str,
    content: str,
    vector: list[float],
) -> KnowledgeChunk:
    document = BusinessInfoDocument(
        merchant_id=merchant_id,
        source=source,
        content=content,
    )
    session.add(document)
    await session.flush()
    chunk = KnowledgeChunk(
        merchant_id=merchant_id,
        document_id=document.id,
        source=source,
        chunk_index=0,
        content=content,
        token_count=2,
        embedding=vector,
        embedding_provider="fake",
        embedding_model="fake-1024",
    )
    session.add(chunk)
    await session.commit()
    return chunk


async def test_retrieval_ranks_relevant_chunk_and_stays_tenant_scoped(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    relevant = await _seed_chunk(
        db_session,
        merchant_id,
        source="policies",
        content="refund policy",
        vector=VECTOR_NEAR,
    )
    irrelevant = await _seed_chunk(
        db_session,
        merchant_id,
        source="about",
        content="hand-dyed silk scarves",
        vector=VECTOR_FAR,
    )

    other = Merchant(name="Other Store", slug=f"pytest-other-{uuid.uuid4().hex[:8]}")
    db_session.add(other)
    await db_session.commit()
    other_merchant = await _seed_chunk(
        db_session,
        other.id,
        source="faq",
        content="refund policy",
        vector=VECTOR_NEAR,
    )

    results = await search_business_info(
        db_session,
        merchant_id,
        "refund",
        provider=QueryEmbeddingProvider(VECTOR_NEAR),
    )

    assert results[0].id == relevant.id
    assert {result.id for result in results} >= {relevant.id, irrelevant.id}
    assert other_merchant.id not in {result.id for result in results}
    assert all(0.0 <= result.score <= 1.0 for result in results)
    assert HYBRID_VECTOR_WEIGHT + HYBRID_TEXT_WEIGHT == 1.0


async def test_retrieval_returns_empty_for_merchant_without_chunks(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    results = await search_business_info(
        db_session,
        merchant_id,
        "refund",
        provider=QueryEmbeddingProvider(VECTOR_NEAR),
    )
    assert results == []


async def test_retrieval_returns_empty_for_blank_query(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    results = await search_business_info(
        db_session,
        merchant_id,
        "   ",
        provider=QueryEmbeddingProvider(VECTOR_NEAR),
    )
    assert results == []


async def test_text_match_can_enter_outside_vector_limit(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    vector_match = await _seed_chunk(
        db_session,
        merchant_id,
        source="about",
        content="silk scarves",
        vector=VECTOR_NEAR,
    )
    text_match = await _seed_chunk(
        db_session,
        merchant_id,
        source="policies",
        content="refund policy",
        vector=VECTOR_FAR,
    )

    results = await search_business_info(
        db_session,
        merchant_id,
        "refund",
        provider=QueryEmbeddingProvider(VECTOR_NEAR),
        vector_limit=1,
        text_limit=5,
    )

    ids = {result.id for result in results}
    assert vector_match.id in ids
    assert text_match.id in ids
