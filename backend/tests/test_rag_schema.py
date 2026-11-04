import uuid

from app.db.models import BusinessInfoDocument, KnowledgeChunk


async def test_knowledge_chunk_table_accepts_a_1024_dim_vector(db_session, merchant_auth):
    merchant_id = uuid.UUID(merchant_auth["merchant"]["id"])
    document = BusinessInfoDocument(merchant_id=merchant_id, source="faq", content="Q: Hours?")
    db_session.add(document)
    await db_session.flush()

    chunk = KnowledgeChunk(
        merchant_id=merchant_id,
        document_id=document.id,
        source="faq",
        chunk_index=0,
        content="Q: Hours?",
        token_count=2,
        embedding=[0.0] * 1024,
        embedding_provider="fake",
        embedding_model="fake-1024",
    )
    db_session.add(chunk)
    await db_session.commit()

    assert chunk.id is not None
