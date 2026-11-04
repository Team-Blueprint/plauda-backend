import pytest

from app.config import get_settings
from app.rag.embedders.cloudflare import CloudflareEmbeddingProvider
from app.rag.embedders.factory import EmbeddingConfigError, get_embedding_provider
from app.rag.embedders.gemini import GeminiEmbeddingProvider
from app.rag.embedders.ollama import OllamaEmbeddingProvider


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_factory_selects_ollama(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama_local")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")

    provider = get_embedding_provider()

    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider.name == "ollama_local"
    assert provider.dims == 1024


def test_factory_selects_cloudflare(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "account-1")
    monkeypatch.setenv("CF_API_TOKEN", "token-1")

    provider = get_embedding_provider()

    assert isinstance(provider, CloudflareEmbeddingProvider)
    assert provider.dims == 1024


def test_factory_selects_gemini(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "key-1")

    provider = get_embedding_provider()

    assert isinstance(provider, GeminiEmbeddingProvider)
    assert provider.dims == 1024


def test_factory_rejects_missing_cloudflare_credentials(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "cloudflare")
    monkeypatch.setenv("CF_ACCOUNT_ID", "")
    monkeypatch.setenv("CF_API_TOKEN", "")

    with pytest.raises(EmbeddingConfigError, match="CF_ACCOUNT_ID"):
        get_embedding_provider()


def test_factory_rejects_missing_gemini_key(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    with pytest.raises(EmbeddingConfigError, match="GEMINI_API_KEY"):
        get_embedding_provider()


def test_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "unknown")

    with pytest.raises(EmbeddingConfigError, match="unknown"):
        get_embedding_provider()
