import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessInfoDocument, KnowledgeChunk
from app.rag.chunker import chunk_markdown
from app.rag.embedders.base import EmbeddingError, EmbeddingProvider, validate_embeddings
from app.rag.embedders.factory import EMBEDDING_DIMS, get_embedding_provider


async def reindex_document(
    session: AsyncSession,
    document: BusinessInfoDocument,
    *,
    provider: EmbeddingProvider | None = None,
) -> int:
    """Replace one document's chunks with a fresh embedding of its current content.

    The embedding call happens before the old rows are deleted, so a provider failure
    leaves the previous index intact.
    """
    chunks = chunk_markdown(document.content)
    if not chunks:
        try:
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        return 0

    provider = provider or get_embedding_provider()
    if provider.dims != EMBEDDING_DIMS:
        raise EmbeddingError(
            f"{provider.name} produces {provider.dims}-dimensional vectors; "
            f"the index requires {EMBEDDING_DIMS}"
        )

    vectors = validate_embeddings(
        await provider.embed([chunk.content for chunk in chunks]),
        expected_count=len(chunks),
        dims=EMBEDDING_DIMS,
        provider=provider.name,
    )

    try:
        await session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
        )
        session.add_all(
            [
                KnowledgeChunk(
                    merchant_id=document.merchant_id,
                    document_id=document.id,
                    source=document.source,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=vector,
                    embedding_provider=provider.name,
                    embedding_model=provider.model,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return len(chunks)


async def reindex_merchant(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    *,
    provider: EmbeddingProvider | None = None,
) -> int:
    """Reindex every business-info document for one merchant."""
    documents = list(
        await session.scalars(
            select(BusinessInfoDocument).where(BusinessInfoDocument.merchant_id == merchant_id)
        )
    )
    if not documents:
        return 0

    provider = provider or get_embedding_provider()
    total = 0
    for document in documents:
        total += await reindex_document(session, document, provider=provider)
    return total
