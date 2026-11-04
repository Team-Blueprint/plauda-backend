import httpx

from app.rag.embedders.base import EmbeddingError, validate_embeddings


class OllamaEmbeddingProvider:
    """Local Ollama embeddings, using bge-m3 by default."""

    name = "ollama_local"
    dims = 1024

    def __init__(
        self,
        base_url: str,
        *,
        model: str = "bge-m3",
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._transport = transport
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                transport=self._transport,
                timeout=self._timeout,
            ) as client:
                response = await client.post(
                    "/api/embed",
                    json={"model": self.model, "input": texts},
                )
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"{self.name} request failed") from exc

        if response.status_code >= 400:
            raise EmbeddingError(f"{self.name} returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingError(f"{self.name} returned invalid JSON") from exc
        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        return validate_embeddings(
            embeddings,
            expected_count=len(texts),
            dims=self.dims,
            provider=self.name,
        )
