import uuid

import pytest
from sqlalchemy import select

from app.db.models import BusinessInfoDocument, KnowledgeChunk
from app.rag.embedders.base import EmbeddingError
from app.rag.reindex import reindex_document, reindex_merchant


class FakeEmbeddingProvider:
    name = "fake"
    model = "fake-1024"
    dims = 1024

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("provider unavailable")


async def _make_document(db_session, merchant_id, content: str) -> BusinessInfoDocument:
    document = BusinessInfoDocument(merchant_id=merchant_id, source="faq", content=content)
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


async def test_reindex_replaces_old_chunks(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    document = await _make_document(
        db_session,
        merchant_id,
        " ".join(f"word{i}" for i in range(500)),
    )
    provider = FakeEmbeddingProvider()

    assert await reindex_document(db_session, document, provider=provider) == 2
    first_ids = set(
        await db_session.scalars(
            select(KnowledgeChunk.id).where(KnowledgeChunk.document_id == document.id)
        )
    )

    assert await reindex_document(db_session, document, provider=provider) == 2
    chunks = list(
        await db_session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
        )
    )

    assert len(chunks) == 2
    assert {chunk.id for chunk in chunks}.isdisjoint(first_ids)
    assert all(chunk.embedding_provider == "fake" for chunk in chunks)


async def test_reindex_empty_content_clears_old_chunks(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    document = await _make_document(db_session, merchant_id, "We ship every Tuesday.")
    provider = FakeEmbeddingProvider()

    assert await reindex_document(db_session, document, provider=provider) == 1
    document.content = ""
    assert await reindex_document(db_session, document, provider=provider) == 0

    chunks = await db_session.scalars(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
    )
    assert list(chunks) == []


async def test_reindex_failure_keeps_old_chunks(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    document = await _make_document(db_session, merchant_id, "Original policy.")
    provider = FakeEmbeddingProvider()
    assert await reindex_document(db_session, document, provider=provider) == 1

    document.content = "Updated policy."
    with pytest.raises(EmbeddingError, match="unavailable"):
        await reindex_document(db_session, document, provider=FailingEmbeddingProvider())

    chunks = list(
        await db_session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
        )
    )
    assert len(chunks) == 1
    assert chunks[0].content == "Original policy."


async def test_reindex_merchant_indexes_all_documents(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    await _make_document(db_session, merchant_id, "FAQ content.")
    second = BusinessInfoDocument(
        merchant_id=merchant_id,
        source="about",
        content="About content.",
    )
    db_session.add(second)
    await db_session.commit()

    assert await reindex_merchant(db_session, merchant_id, provider=FakeEmbeddingProvider()) == 2
