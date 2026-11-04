# AI RAG Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a merchant's approved business info chunkable, embeddable, and searchable through a tenant-scoped hybrid retrieval service.

**Architecture:** Store 1024-dimension embeddings in Supabase Postgres with pgvector and a generated full-text vector. A provider-agnostic embedding interface supports Cloudflare, Ollama, and Gemini. Business-info saves reindex their own document; retrieval combines cosine similarity with PostgreSQL full-text ranking.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, pgvector, httpx, pytest

**Spec:** `BUILD_PLAN.md` §5 (embeddings/retrieval), §4.2 (`search_business_info`), `docs/ai.md`

## Global Constraints

- Embedding dimensions are **1024** for every provider.
- Only `about`, `policies`, and `faq` markdown documents are embedded.
- Every query filters by `merchant_id`; no cross-tenant retrieval.
- Prices and stock are never retrieved from vectors.
- One active embedding provider per index; every chunk records `embedding_provider` and
  `embedding_model`.
- Provider failures must not corrupt or mix the index.
- RAG tests must run offline with deterministic fake embeddings.

## Review Focus

1. A merchant with no business-info documents must get an empty result, not an error.
2. Re-saving a document must replace its old chunks, not accumulate duplicates.
3. A chunk embedding with a different dimension or provider must be rejected.
4. A retrieval query for another merchant must return no rows.
5. Provider HTTP errors or malformed responses must not leave partial chunks behind.

---

### Task 1: pgvector schema and model

**Files:**
- Modify: `backend/pyproject.toml` (add `pgvector`)
- Modify: `backend/app/db/models.py`
- Create: `backend/alembic/versions/0006_knowledge_chunks.py`
- Modify: `backend/tests/conftest.py` (ensure vector extension before `create_all`)
- Test: `backend/tests/test_rag_schema.py`

**Interfaces:**
- Produces: `KnowledgeChunk` SQLAlchemy model with `merchant_id`, `document_id`, `source`,
  `chunk_index`, `content`, `token_count`, `embedding`, `embedding_provider`,
  `embedding_model`, `tsv`, `created_at`.
- Produces: unique constraint `(document_id, chunk_index)` and indexes
  `(merchant_id)`, HNSW on `embedding vector_cosine_ops`, GIN on `tsv`.

- [ ] **Step 1: Write the failing schema test**

```python
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
```

- [ ] **Step 2: Run it and verify it fails**

Run: `uv run pytest tests/test_rag_schema.py::test_knowledge_chunk_table_accepts_a_1024_dim_vector -q`
Expected: FAIL because `KnowledgeChunk` does not exist.

- [ ] **Step 3: Add dependency, model, and migration**

Add `pgvector>=0.3` to `backend/pyproject.toml` and run `uv sync`.

Add to `app/db/models.py`:

```python
from pgvector.sqlalchemy import Vector

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunks_document_index"),
        CheckConstraint("source IN ('about', 'policies', 'faq')", name="ck_knowledge_chunks_source"),
        Index("ix_knowledge_chunks_merchant_id", "merchant_id"),
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_knowledge_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business_info_documents.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(80), nullable=False)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', content)", persisted=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Migration `0006_knowledge_chunks.py`:

```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
op.create_table("knowledge_chunks", ...)
op.create_index("ix_knowledge_chunks_merchant_id", "knowledge_chunks", ["merchant_id"])
op.create_index(
    "ix_knowledge_chunks_embedding_hnsw",
    "knowledge_chunks",
    ["embedding"],
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
op.create_index("ix_knowledge_chunks_tsv", "knowledge_chunks", ["tsv"], postgresql_using="gin")
```

Use `postgresql.UUID(as_uuid=True)`, `Vector(1024)`, `TSVECTOR`, and `sa.Computed` in the
migration. Add the same `CREATE EXTENSION` call to the test fixture before
`Base.metadata.create_all`.

- [ ] **Step 4: Run the schema test**

Run: `uv run pytest tests/test_rag_schema.py::test_knowledge_chunk_table_accepts_a_1024_dim_vector -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/db/models.py backend/alembic/versions/0006_knowledge_chunks.py backend/tests/conftest.py backend/tests/test_rag_schema.py
git commit -m "feat(rag): add pgvector knowledge chunk schema"
```

---

### Task 2: Markdown chunker

**Files:**
- Create: `backend/app/rag/__init__.py`
- Create: `backend/app/rag/chunker.py`
- Test: `backend/tests/test_rag_chunker.py`

**Interfaces:**
- Produces: `Chunk` dataclass with `index: int`, `content: str`, `token_count: int`.
- Produces: `chunk_markdown(text: str, *, max_tokens: int = 400, overlap_tokens: int = 50) -> list[Chunk]`.

- [ ] **Step 1: Write failing chunker tests**

```python
def test_empty_markdown_returns_no_chunks():
    assert chunk_markdown("   \n") == []

def test_short_markdown_is_one_chunk():
    chunks = chunk_markdown("We deliver in Lagos within 2 days.")
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].token_count == 7

def test_long_markdown_overlaps_chunks():
    text = " ".join(f"word{i}" for i in range(1000))
    chunks = chunk_markdown(text, max_tokens=100, overlap_tokens=20)
    assert len(chunks) > 1
    assert all(chunk.token_count <= 100 for chunk in chunks)
    assert chunks[0].content.split()[-20:] == chunks[1].content.split()[:20]
    assert chunks[0].index == 0 and chunks[1].index == 1
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_rag_chunker.py -q`
Expected: FAIL because `chunk_markdown` does not exist.

- [ ] **Step 3: Implement the chunker**

Use whitespace tokens, preserve order, and reject `overlap_tokens >= max_tokens`. The final chunk
may be shorter than `max_tokens`. Do not merge headings or strip content beyond whitespace
normalization.

- [ ] **Step 4: Run and verify pass**

Run: `uv run pytest tests/test_rag_chunker.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/__init__.py backend/app/rag/chunker.py backend/tests/test_rag_chunker.py
git commit -m "feat(rag): add markdown chunker"
```

---

### Task 3: Embedding interface and Ollama adapter

**Files:**
- Create: `backend/app/rag/embedders/__init__.py`
- Create: `backend/app/rag/embedders/base.py`
- Create: `backend/app/rag/embedders/ollama.py`
- Test: `backend/tests/test_rag_embedders.py`

**Interfaces:**
- Produces: `EmbeddingProvider` protocol with `name`, `model`, `dims`, and
  `async embed(texts: list[str]) -> list[list[float]]`.
- Produces: `OllamaEmbeddingProvider(base_url: str, model: str = "bge-m3", transport=None)`.
- Produces: `EmbeddingError(RuntimeError)`.

- [ ] **Step 1: Write failing Ollama tests**

Use `httpx.MockTransport` to assert:

```python
async def test_ollama_embedding_request_and_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.1] * 1024, [0.2] * 1024]})

    provider = OllamaEmbeddingProvider(
        "http://ollama:11434", transport=httpx.MockTransport(handler)
    )
    vectors = await provider.embed(["hello", "world"])
    assert seen["path"] == "/api/embed"
    assert seen["json"] == {"model": "bge-m3", "input": ["hello", "world"]}
    assert len(vectors) == 2
    assert len(vectors[0]) == 1024
```

Add a malformed-response test expecting `EmbeddingError`.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_rag_embedders.py -q`
Expected: FAIL because the provider does not exist.

- [ ] **Step 3: Implement the protocol and Ollama adapter**

Use an injectable `httpx.AsyncClient` transport. Validate that the response contains one embedding
per input and each vector has exactly 1024 floats. Raise `EmbeddingError` on HTTP or shape errors.

- [ ] **Step 4: Run and verify pass**

Run: `uv run pytest tests/test_rag_embedders.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/embedders backend/tests/test_rag_embedders.py
git commit -m "feat(rag): add embedding interface and Ollama adapter"
```

---

### Task 4: Cloudflare and Gemini adapters

**Files:**
- Create: `backend/app/rag/embedders/cloudflare.py`
- Create: `backend/app/rag/embedders/gemini.py`
- Modify: `backend/tests/test_rag_embedders.py`

**Interfaces:**
- Produces: `CloudflareEmbeddingProvider(account_id: str, api_token: str, model: str = "@cf/baai/bge-m3", transport=None)`.
- Produces: `GeminiEmbeddingProvider(api_key: str, model: str = "gemini-embedding-001", dims: int = 1024, transport=None)`.
- Both expose `name`, `model`, `dims`, and `embed`.

- [ ] **Step 1: Write failing adapter tests**

For Cloudflare, assert:

```text
POST /client/v4/accounts/{account_id}/ai/run/@cf/baai/bge-m3
Authorization: Bearer <token>
body: {"text": ["hello"]}
response: {"result": {"data": [[0.1, ... 1024]]}}
```

For Gemini, assert:

```text
POST /v1beta/models/gemini-embedding-001:batchEmbedContents?key=<key>
body.requests[0].content.parts[0].text == "hello"
body.requests[0].outputDimensionality == 1024
response: {"embeddings": [{"values": [0.1, ... 1024]}]}
```

Add malformed-response tests.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_rag_embedders.py -q`
Expected: FAIL because the adapters do not exist.

- [ ] **Step 3: Implement both adapters**

Both validate count and 1024 dimensions. Both raise `EmbeddingError` on bad status or bad shape.
Do not log API keys or request authorization headers.

- [ ] **Step 4: Run and verify pass**

Run: `uv run pytest tests/test_rag_embedders.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/embedders/cloudflare.py backend/app/rag/embedders/gemini.py backend/tests/test_rag_embedders.py
git commit -m "feat(rag): add Cloudflare and Gemini embedding adapters"
```

---

### Task 5: Provider factory

**Files:**
- Create: `backend/app/rag/embedders/factory.py`
- Test: `backend/tests/test_rag_factory.py`

**Interfaces:**
- Produces: `get_embedding_provider(settings=None) -> EmbeddingProvider`.
- Produces: `EmbeddingConfigError(EmbeddingError)`.
- Consumes: settings fields `embedding_provider`, `cf_account_id`, `cf_api_token`,
  `gemini_api_key`, `ollama_base_url`.

- [ ] **Step 1: Write failing factory tests**

```python
def test_factory_selects_ollama(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama_local")
    get_settings.cache_clear()
    provider = get_embedding_provider()
    assert provider.name == "ollama_local"
    assert provider.dims == 1024

def test_factory_rejects_missing_cloudflare_credentials(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "")
    get_settings.cache_clear()
    with pytest.raises(EmbeddingConfigError):
        get_embedding_provider()
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_rag_factory.py -q`
Expected: FAIL because the factory does not exist.

- [ ] **Step 3: Implement the factory**

Support `ollama_local`, `cloudflare`, and `gemini`; raise `EmbeddingConfigError` for unknown
providers or missing required settings.

- [ ] **Step 4: Run and verify pass**

Run: `uv run pytest tests/test_rag_factory.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/embedders/factory.py backend/tests/test_rag_factory.py
git commit -m "feat(rag): add embedding provider factory"
```

---

### Task 6: Reindex a business-info document

**Files:**
- Create: `backend/app/rag/reindex.py`
- Test: `backend/tests/test_rag_reindex.py`

**Interfaces:**
- Produces: `async reindex_document(session, document, *, provider=None) -> int`.
- Behavior: chunk the document, embed all chunks, delete the document's existing chunks, insert the
  new chunks with provider/model metadata, commit, and return the chunk count.
- Produces: `async reindex_merchant(session, merchant_id, *, provider=None) -> int`.

- [ ] **Step 1: Write failing reindex tests**

Use a fake provider returning deterministic 1024-dim vectors.

```python
async def test_reindex_replaces_old_chunks(db_session, merchant_auth):
    ...
    assert await reindex_document(db_session, document, provider=fake) == 2
    assert await reindex_document(db_session, document, provider=fake) == 2
    chunks = await db_session.scalars(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
    )
    assert len(chunks.all()) == 2
```

Add tests for empty content clearing old chunks and for provider failure leaving the old chunks in
place.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_rag_reindex.py -q`
Expected: FAIL because `reindex_document` does not exist.

- [ ] **Step 3: Implement the reindex service**

Embed before deleting old rows so a provider failure is atomic. Use `await session.delete` or a
delete statement inside the transaction. Never mix providers in one document; replacement chunks
carry the active provider/model.

- [ ] **Step 4: Run and verify pass**

Run: `uv run pytest tests/test_rag_reindex.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/reindex.py backend/tests/test_rag_reindex.py
git commit -m "feat(rag): reindex business info documents"
```

---

### Task 7: Hybrid retrieval

**Files:**
- Create: `backend/app/rag/retrieval.py`
- Test: `backend/tests/test_rag_retrieval.py`

**Interfaces:**
- Produces: `RetrievedChunk` dataclass with `id`, `source`, `content`, `score`.
- Produces: `async search_business_info(session, merchant_id, query, *, provider=None, vector_limit=8, text_limit=5) -> list[RetrievedChunk]`.
- Produces: `HYBRID_VECTOR_WEIGHT = 0.7`, `HYBRID_TEXT_WEIGHT = 0.3`.

- [ ] **Step 1: Write failing retrieval tests**

Seed two merchants with chunks and deterministic embeddings. Assert:

- the relevant chunk ranks first
- another merchant's chunk is never returned
- an empty corpus returns `[]`
- text-only matches still appear
- the returned score is between 0 and 1

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_rag_retrieval.py -q`
Expected: FAIL because the retrieval service does not exist.

- [ ] **Step 3: Implement hybrid SQL**

Use:

```text
vector_score = 1 - (embedding <=> query_vector)
text_score   = ts_rank_cd(tsv, websearch_to_tsquery('simple', query))
score        = 0.7 * vector_score + 0.3 * text_score
```

Fetch vector top-8 and full-text top-5 separately, union by chunk ID, sum the weighted scores, and
order by score descending. Filter every branch by `merchant_id`. Return no rows for a blank query.

- [ ] **Step 4: Run and verify pass**

Run: `uv run pytest tests/test_rag_retrieval.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/retrieval.py backend/tests/test_rag_retrieval.py
git commit -m "feat(rag): add tenant-scoped hybrid retrieval"
```

---

### Task 8: Wire business-info saves and document the slice

**Files:**
- Modify: `backend/app/merchants/business_info.py`
- Modify: `backend/tests/test_business_info_api.py`
- Modify: `docs/ai.md`
- Modify: `docs/status.md`
- Modify: `docs/architecture.md`
- Modify: `docs/contracts/openapi.json` if the API surface changes

**Interfaces:**
- Consumes: `reindex_document` from Task 6.
- Behavior: after saving a business-info document, attempt a reindex; a provider failure logs a
  warning but does not fail the save.

- [ ] **Step 1: Write a failing API test**

Monkeypatch `reindex_document` to a fake and assert `PUT /business-info/faq` calls it once after
the document is committed. Add a second test where reindex raises and the save still returns
`200`.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_business_info_api.py -q`
Expected: FAIL because the route does not call reindex.

- [ ] **Step 3: Wire best-effort reindexing**

Use `try/except EmbeddingError` (and unexpected exceptions with `logger.exception`) after commit.
Do not roll back the saved document.

- [ ] **Step 4: Run the full targeted suite**

Run:

```bash
uv run pytest tests/test_rag_chunker.py tests/test_rag_embedders.py tests/test_rag_factory.py \
  tests/test_rag_reindex.py tests/test_rag_retrieval.py tests/test_business_info_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/merchants/business_info.py backend/tests/test_business_info_api.py \
  docs/ai.md docs/status.md docs/architecture.md docs/contracts/openapi.json
git commit -m "feat(rag): reindex business info on save"
```

---

## Verification gate

Before starting Slice B:

```bash
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run alembic check
```

The slice is complete when a seeded merchant's FAQ/policy text can be chunked, reindexed, and
retrieved by a tenant-scoped hybrid query with deterministic tests, and the migration applies to a
fresh database with pgvector enabled.
