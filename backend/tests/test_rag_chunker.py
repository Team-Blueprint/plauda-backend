import pytest

from app.rag.chunker import chunk_markdown


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


def test_rejects_invalid_overlap():
    with pytest.raises(ValueError, match="overlap"):
        chunk_markdown("hello world", max_tokens=10, overlap_tokens=10)
