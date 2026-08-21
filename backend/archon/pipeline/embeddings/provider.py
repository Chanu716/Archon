import abc
from typing import List
import structlog
import httpx
from archon.config import settings

logger = structlog.get_logger(__name__)

class EmbeddingProvider(abc.ABC):
    """
    Abstract base class for embedding models.
    Converts semantic source text into dense vector representations.
    """
    
    @abc.abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Generate an embedding for a single text."""
        pass
        
    @abc.abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        pass

class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Ollama implementation for generating local embeddings without API keys.
    """
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip('/')
        self.model = settings.EMBEDDING_MODEL

    async def embed(self, text: str) -> List[float]:
        if not text.strip():
            return [0.0] * settings.EMBEDDING_DIMENSIONS
            
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": text
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["embeddings"][0]
        except Exception as e:
            logger.warning("ollama_embed_failed_fallback_dummy", error=str(e), model=self.model)
            return [0.0] * settings.EMBEDDING_DIMENSIONS

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        valid_texts = [t if t.strip() else " " for t in texts]
        
        if not valid_texts:
            return []
            
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": valid_texts
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["embeddings"]
        except Exception as e:
            logger.warning("ollama_embed_batch_failed_fallback_dummy", error=str(e), batch_size=len(texts), model=self.model)
            return [[0.0] * settings.EMBEDDING_DIMENSIONS for _ in texts]

class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini AI Studio free text embedding provider."""
    def __init__(self):
        self.api_key = (settings.GEMINI_API_KEY or "").strip()
        self.model = "text-embedding-004"

    async def embed(self, text: str) -> List[float]:
        if not text.strip() or not self.api_key:
            return [0.0] * settings.EMBEDDING_DIMENSIONS
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent?key={self.api_key}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json={"content": {"parts": [{"text": text[:2000]}]}})
                if res.status_code != 200:
                    logger.warning("gemini_embed_status_error", status=res.status_code)
                    return [0.0] * settings.EMBEDDING_DIMENSIONS
                data = res.json()
                values = data.get("embedding", {}).get("values", [])
                if not values:
                    return [0.0] * settings.EMBEDDING_DIMENSIONS
                if len(values) < settings.EMBEDDING_DIMENSIONS:
                    values = values + [0.0] * (settings.EMBEDDING_DIMENSIONS - len(values))
                return values[:settings.EMBEDDING_DIMENSIONS]
        except Exception as e:
            logger.warning("gemini_embed_failed_fallback", error=str(e))
            return [0.0] * settings.EMBEDDING_DIMENSIONS

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts or not self.api_key:
            return [[0.0] * settings.EMBEDDING_DIMENSIONS for _ in texts]
        
        valid_texts = [t if t.strip() else " " for t in texts]
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents?key={self.api_key}"
            requests_payload = [{"model": f"models/{self.model}", "content": {"parts": [{"text": t[:2000]}]}} for t in valid_texts]
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(url, json={"requests": requests_payload})
                if res.status_code == 200:
                    data = res.json()
                    embeddings_raw = data.get("embeddings", [])
                    results = []
                    for item in embeddings_raw:
                        values = item.get("values", [])
                        if len(values) < settings.EMBEDDING_DIMENSIONS:
                            values = values + [0.0] * (settings.EMBEDDING_DIMENSIONS - len(values))
                        results.append(values[:settings.EMBEDDING_DIMENSIONS])
                    if len(results) == len(texts):
                        return results
        except Exception as e:
            logger.warning("gemini_batch_embed_failed_fallback", error=str(e))

        # Fallback to individual embed
        results = []
        for text in texts:
            emb = await self.embed(text)
            results.append(emb)
        return results

class DummyEmbeddingProvider(EmbeddingProvider):
    """Fallback provider when running in cloud without local models."""
    async def embed(self, text: str) -> List[float]:
        return [0.0] * settings.EMBEDDING_DIMENSIONS
        
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [[0.0] * settings.EMBEDDING_DIMENSIONS for _ in texts]

def get_embedding_provider() -> EmbeddingProvider:
    """Factory to get the configured embedding provider."""
    provider_name = (settings.EMBEDDING_PROVIDER or "").lower()
    
    if provider_name == "gemini":
        return GeminiEmbeddingProvider()
    elif provider_name == "ollama":
        return OllamaEmbeddingProvider()
    elif provider_name == "dummy":
        return DummyEmbeddingProvider()
    elif not provider_name:
        if settings.GEMINI_API_KEY:
            return GeminiEmbeddingProvider()
        return DummyEmbeddingProvider()
    else:
        raise ValueError(f"Unsupported embedding provider: {provider_name}")
