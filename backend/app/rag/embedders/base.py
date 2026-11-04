import math
from collections.abc import Sequence
from typing import Protocol, runtime_checkable


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider cannot produce a valid vector list."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Provider-agnostic interface used by indexing and retrieval."""

    name: str
    model: str
    dims: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...


def validate_embeddings(
    vectors: object,
    *,
    expected_count: int,
    dims: int,
    provider: str,
) -> list[list[float]]:
    """Validate provider output before it can enter the vector index."""
    if not isinstance(vectors, list):
        raise EmbeddingError(f"{provider} returned a non-list embeddings payload")
    if len(vectors) != expected_count:
        raise EmbeddingError(
            f"{provider} returned {len(vectors)} embeddings for {expected_count} inputs"
        )

    validated: list[list[float]] = []
    for index, vector in enumerate(vectors):
        if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes)):
            raise EmbeddingError(f"{provider} embedding {index} is not a list")
        if len(vector) != dims:
            raise EmbeddingError(
                f"{provider} embedding {index} has dimension {len(vector)}; expected {dims}"
            )

        values: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EmbeddingError(f"{provider} embedding {index} contains a non-number")
            number = float(value)
            if not math.isfinite(number):
                raise EmbeddingError(f"{provider} embedding {index} contains a non-finite value")
            values.append(number)
        validated.append(values)

    return validated
