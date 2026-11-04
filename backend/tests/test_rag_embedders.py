import json

import httpx
import pytest

from app.rag.embedders.base import EmbeddingError
from app.rag.embedders.cloudflare import CloudflareEmbeddingProvider
from app.rag.embedders.gemini import GeminiEmbeddingProvider
from app.rag.embedders.ollama import OllamaEmbeddingProvider


def _vector(value: float = 0.1) -> list[float]:
    return [value] * 1024


async def test_ollama_embedding_request_and_response():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"embeddings": [_vector(0.1), _vector(0.2)]},
        )

    provider = OllamaEmbeddingProvider(
        "http://ollama:11434", transport=httpx.MockTransport(handler)
    )
    vectors = await provider.embed(["hello", "world"])

    assert provider.name == "ollama_local"
    assert provider.model == "bge-m3"
    assert provider.dims == 1024
    assert seen["path"] == "/api/embed"
    assert seen["json"] == {"model": "bge-m3", "input": ["hello", "world"]}
    assert vectors == [_vector(0.1), _vector(0.2)]


async def test_ollama_rejects_malformed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1]]})

    provider = OllamaEmbeddingProvider(
        "http://ollama:11434", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(EmbeddingError, match="1024"):
        await provider.embed(["hello"])


async def test_ollama_empty_input_skips_http():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    provider = OllamaEmbeddingProvider(
        "http://ollama:11434", transport=httpx.MockTransport(handler)
    )
    assert await provider.embed([]) == []


async def test_cloudflare_embedding_request_and_response():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"result": {"data": [_vector(0.3)]}})

    provider = CloudflareEmbeddingProvider(
        account_id="account-1",
        api_token="token-1",
        transport=httpx.MockTransport(handler),
    )
    vectors = await provider.embed(["hello"])

    assert provider.name == "cloudflare"
    assert provider.dims == 1024
    assert seen["path"] == "/client/v4/accounts/account-1/ai/run/@cf/baai/bge-m3"
    assert seen["auth"] == "Bearer token-1"
    assert seen["json"] == {"text": ["hello"]}
    assert vectors == [_vector(0.3)]


async def test_cloudflare_rejects_malformed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"data": "not-a-list"}})

    provider = CloudflareEmbeddingProvider(
        account_id="account-1",
        api_token="token-1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingError):
        await provider.embed(["hello"])


async def test_gemini_embedding_request_and_response():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [{"values": _vector(0.4)}]})

    provider = GeminiEmbeddingProvider(
        api_key="key-1",
        transport=httpx.MockTransport(handler),
    )
    vectors = await provider.embed(["hello"])

    assert provider.name == "gemini"
    assert provider.model == "gemini-embedding-001"
    assert provider.dims == 1024
    assert seen["path"] == "/v1beta/models/gemini-embedding-001:batchEmbedContents"
    assert seen["key"] == "key-1"
    assert seen["json"] == {
        "requests": [
            {
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": "hello"}]},
                "outputDimensionality": 1024,
            }
        ]
    }
    assert vectors == [_vector(0.4)]


async def test_gemini_rejects_malformed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [{"values": [0.1]}]})

    provider = GeminiEmbeddingProvider(
        api_key="key-1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingError):
        await provider.embed(["hello"])
