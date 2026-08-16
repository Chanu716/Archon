import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
import json

from archon.pipeline.llm.provider import OpenRouterProvider, GeminiProvider, GroqProvider, OllamaProvider, get_llm_provider
from archon.models.analyst import AnalystResponse

@pytest.fixture
def mock_httpx_post():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        yield mock_post

@pytest.fixture
def mock_httpx_stream():
    with patch("httpx.AsyncClient.stream") as mock_stream:
        yield mock_stream

@pytest.mark.asyncio
async def test_ollama_analyze(mock_httpx_post, monkeypatch):
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.LLM_PROVIDER", "ollama")
    provider = OllamaProvider()
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"answer": "test answer", "confidence": "HIGH", "uncertainties": [], "referenced_evidence_ids": ["E1"]}'
                }
            }
        ]
    }
    mock_httpx_post.return_value = mock_response

    result = await provider.analyze("sys prompt", "context", "question")
    
    assert result.answer == "test answer"
    assert result.confidence == "HIGH"
    assert result.referenced_evidence_ids == ["E1"]

@pytest.mark.asyncio
async def test_ollama_analyze_stream(mock_httpx_stream, monkeypatch):
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.LLM_PROVIDER", "ollama")
    provider = OllamaProvider()
    
    # Mock stream response and aiter_lines
    mock_response = MagicMock()
    
    async def mock_aiter_lines():
        lines = [
            'data: {"choices":[{"delta":{"content":"Part 1"}}]}',
            'data: {"choices":[{"delta":{"content":" Part 2"}}]}',
            'data: [DONE]'
        ]
        for line in lines:
            yield line
            
    mock_response.aiter_lines = mock_aiter_lines
    
    # httpx.AsyncClient.stream is an async context manager
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__.return_value = mock_response
    mock_httpx_stream.return_value = mock_context_manager
    
    chunks = []
    async for chunk in provider.analyze_stream("sys", "ctx", "q"):
        chunks.append(chunk)
        
    assert chunks == ["Part 1", " Part 2"]

def test_get_llm_provider_openrouter(monkeypatch):
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.LLM_PROVIDER", "openrouter")
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.OPENROUTER_API_KEY", "test-key")
    provider = get_llm_provider()
    assert isinstance(provider, OpenRouterProvider)
    
def test_get_llm_provider_gemini(monkeypatch):
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.LLM_PROVIDER", "gemini")
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.GEMINI_API_KEY", "test-key")
    provider = get_llm_provider()
    assert isinstance(provider, GeminiProvider)

def test_get_llm_provider_groq(monkeypatch):
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.LLM_PROVIDER", "groq")
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.GROQ_API_KEY", "test-key")
    provider = get_llm_provider()
    assert isinstance(provider, GroqProvider)

def test_get_llm_provider_ollama(monkeypatch):
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.LLM_PROVIDER", "ollama")
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)

def test_get_llm_provider_unknown(monkeypatch):
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.LLM_PROVIDER", "unknown_provider")
    with pytest.raises(ValueError, match="Unsupported LLM provider: unknown_provider"):
        get_llm_provider()

def test_provider_missing_key_raises(monkeypatch):
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.LLM_PROVIDER", "openrouter")
    monkeypatch.setattr("archon.pipeline.llm.provider.settings.OPENROUTER_API_KEY", None)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is not configured"):
        get_llm_provider()
