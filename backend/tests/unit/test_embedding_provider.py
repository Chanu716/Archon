import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from archon.pipeline.embeddings.provider import OllamaEmbeddingProvider, get_embedding_provider

@pytest.fixture
def mock_httpx_post():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        yield mock_post

@pytest.mark.asyncio
async def test_ollama_embed(mock_httpx_post, monkeypatch):
    monkeypatch.setattr("archon.pipeline.embeddings.provider.settings.EMBEDDING_PROVIDER", "ollama")
    provider = OllamaEmbeddingProvider()
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "embeddings": [
            [0.1, 0.2, 0.3]
        ]
    }
    mock_httpx_post.return_value = mock_response

    result = await provider.embed("test text")
    assert result == [0.1, 0.2, 0.3]

@pytest.mark.asyncio
async def test_ollama_embed_batch(mock_httpx_post, monkeypatch):
    monkeypatch.setattr("archon.pipeline.embeddings.provider.settings.EMBEDDING_PROVIDER", "ollama")
    provider = OllamaEmbeddingProvider()
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "embeddings": [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6]
        ]
    }
    mock_httpx_post.return_value = mock_response

    result = await provider.embed_batch(["text1", "text2"])
    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

def test_get_embedding_provider(monkeypatch):
    monkeypatch.setattr("archon.pipeline.embeddings.provider.settings.EMBEDDING_PROVIDER", "ollama")
    provider = get_embedding_provider()
    assert isinstance(provider, OllamaEmbeddingProvider)

def test_get_embedding_provider_unknown(monkeypatch):
    monkeypatch.setattr("archon.pipeline.embeddings.provider.settings.EMBEDDING_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="Unsupported embedding provider: unknown"):
        get_embedding_provider()
