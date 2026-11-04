import httpx

from app.rag.embedders.base import EmbeddingError, validate_embeddings


class GeminiEmbeddingProvider:
    """Google Gemini embeddings, normalized to 1024 dimensions for this index."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-embedding-001",
        dims: int = 1024,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required")
        self._api_key = api_key
        self.model = model
        self.dims = dims
        self._transport = transport
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        requests = [
            {
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": self.dims,
            }
            for text in texts
        ]
        try:
            async with httpx.AsyncClient(
                base_url="https://generativelanguage.googleapis.com",
                transport=self._transport,
                timeout=self._timeout,
            ) as client:
                response = await client.post(
                    f"/v1beta/models/{self.model}:batchEmbedContents",
                    headers={"x-goog-api-key": self._api_key},
                    json={"requests": requests},
                )
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"{self.name} request failed") from exc

        if response.status_code >= 400:
            raise EmbeddingError(f"{self.name} returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingError(f"{self.name} returned invalid JSON") from exc

        raw_embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(raw_embeddings, list):
            embeddings = None
        else:
            embeddings = [
                item.get("values") if isinstance(item, dict) else None for item in raw_embeddings
            ]

        return validate_embeddings(
            embeddings,
            expected_count=len(texts),
            dims=self.dims,
            provider=self.name,
        )
