from app.config import Settings, get_settings
from app.rag.embedders.base import EmbeddingError, EmbeddingProvider
from app.rag.embedders.cloudflare import CloudflareEmbeddingProvider
from app.rag.embedders.gemini import GeminiEmbeddingProvider
from app.rag.embedders.ollama import OllamaEmbeddingProvider

EMBEDDING_DIMS = 1024


class EmbeddingConfigError(EmbeddingError):
    """Raised when the configured provider is unknown or missing credentials."""


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    provider = settings.embedding_provider.strip().lower()

    if provider == "ollama_local":
        return OllamaEmbeddingProvider(settings.ollama_base_url)

    if provider == "cloudflare":
        if not settings.cf_account_id.strip():
            raise EmbeddingConfigError("CF_ACCOUNT_ID is required for cloudflare embeddings")
        if not settings.cf_api_token.strip():
            raise EmbeddingConfigError("CF_API_TOKEN is required for cloudflare embeddings")
        return CloudflareEmbeddingProvider(settings.cf_account_id, settings.cf_api_token)

    if provider == "gemini":
        if not settings.gemini_api_key.strip():
            raise EmbeddingConfigError("GEMINI_API_KEY is required for gemini embeddings")
        return GeminiEmbeddingProvider(settings.gemini_api_key, dims=EMBEDDING_DIMS)

    raise EmbeddingConfigError(f"unknown embedding provider: {settings.embedding_provider!r}")
