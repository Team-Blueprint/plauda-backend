from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """One embeddable slice of a merchant document."""

    index: int
    content: str
    token_count: int


def chunk_markdown(
    text: str,
    *,
    max_tokens: int = 400,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Split text into overlapping whitespace-token windows.

    This is intentionally a simple approximation of a model tokenizer. It keeps
    the storage contract stable while avoiding a heavyweight tokenizer dependency.
    Markdown structure is not preserved; chunk text is for retrieval and citation.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must not be negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    words = text.split()
    if not words:
        return []

    chunks: list[Chunk] = []
    start = 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        chunk_words = words[start:end]
        chunks.append(
            Chunk(
                index=len(chunks),
                content=" ".join(chunk_words),
                token_count=len(chunk_words),
            )
        )
        if end == len(words):
            break
        start = end - overlap_tokens

    return chunks
