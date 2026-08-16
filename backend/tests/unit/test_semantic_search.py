import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from archon.services.semantic_search import SemanticSearchService

@pytest.fixture
def mock_provider():
    with patch("archon.services.semantic_search.get_embedding_provider") as mock_get_provider:
        provider = MagicMock()
        provider.embed = AsyncMock(return_value=[0.1] * 1536)
        mock_get_provider.return_value = provider
        yield provider


@pytest.mark.asyncio
async def test_semantic_search_with_snapshot(mock_provider):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    
    # Mock database row returns (CodeEmbedding, distance)
    mock_embedding = MagicMock()
    mock_embedding.entity_id = "test_func"
    mock_embedding.entity_type = "Function"
    mock_embedding.file_path = "test.py"
    mock_embedding.source_text = "def test_func(): pass"
    mock_embedding.snapshot_id = uuid.uuid4()
    
    mock_result.all.return_value = [(mock_embedding, 0.1)]
    mock_db.execute.return_value = mock_result
    
    service = SemanticSearchService(mock_db)
    
    repo_id = uuid.uuid4()
    snap_id = uuid.uuid4()
    
    results = await service.search(
        repository_id=repo_id,
        snapshot_id=snap_id,
        query="test query",
        limit=5
    )
    
    assert len(results) == 1
    assert results[0]["entity"] == "test_func"
    assert results[0]["similarity"] == 0.9  # 1.0 - 0.1
    
    # Provider called
    mock_provider.embed.assert_called_once_with("test query")
