import httpx

from app.rag.embedders.base import EmbeddingError, validate_embeddings


class CloudflareEmbeddingProvider:
    """Cloudflare Workers AI embeddings, using BGE-M3."""

    name = "cloudflare"
    dims = 1024

    def __init__(
        self,
        account_id: str,
        api_token: str,
        *,
        model: str = "@cf/baai/bge-m3",
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not account_id.strip():
            raise ValueError("account_id is required")
        if not api_token.strip():
            raise ValueError("api_token is required")
        self.account_id = account_id
        self.model = model
        self._api_token = api_token
        self._transport = transport
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        path = f"/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
        try:
            async with httpx.AsyncClient(
                base_url="https://api.cloudflare.com",
                transport=self._transport,
                timeout=self._timeout,
                headers={"Authorization": f"Bearer {self._api_token}"},
            ) as client:
                response = await client.post(path, json={"text": texts})
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"{self.name} request failed") from exc

        if response.status_code >= 400:
            raise EmbeddingError(f"{self.name} returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingError(f"{self.name} returned invalid JSON") from exc

        result = payload.get("result") if isinstance(payload, dict) else None
        embeddings = result.get("data") if isinstance(result, dict) else None
        return validate_embeddings(
            embeddings,
            expected_count=len(texts),
            dims=self.dims,
            provider=self.name,
        )
