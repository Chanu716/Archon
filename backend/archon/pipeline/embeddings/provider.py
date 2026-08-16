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
        # Default to http://localhost:11434 if not provided
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
            logger.error("ollama_embed_failed", error=str(e), model=self.model)
            raise

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
            logger.error("ollama_embed_batch_failed", error=str(e), batch_size=len(texts), model=self.model)
            raise

class DummyEmbeddingProvider(EmbeddingProvider):
    """Fallback provider when something fails completely."""
    async def embed(self, text: str) -> List[float]:
        return [0.0] * settings.EMBEDDING_DIMENSIONS
        
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [[0.0] * settings.EMBEDDING_DIMENSIONS for _ in texts]

def get_embedding_provider() -> EmbeddingProvider:
    """Factory to get the configured embedding provider."""
    provider_name = settings.EMBEDDING_PROVIDER.lower() if hasattr(settings, "EMBEDDING_PROVIDER") and settings.EMBEDDING_PROVIDER else "ollama"
    
    if provider_name == "ollama":
        return OllamaEmbeddingProvider()
    else:
        raise ValueError(f"Unsupported embedding provider: {provider_name}")
