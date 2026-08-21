import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from archon.services.investigation_service import InvestigationService
from archon.models.investigation import InvestigationContext
from fastapi import HTTPException

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def repo_id():
    return uuid.uuid4()

@pytest.fixture
def snapshot_id():
    return uuid.uuid4()

@pytest.mark.asyncio
async def test_get_context_success(mock_db, repo_id, snapshot_id):
    service = InvestigationService(mock_db, repo_id)
    
    with patch.object(service, '_resolve_snapshot_id', return_value=snapshot_id):
        with patch('archon.services.investigation_service.GraphService') as mock_graph_class:
            mock_graph = mock_graph_class.return_value
            mock_graph.get_node_details = AsyncMock(return_value={
                "data": {
                    "id": "node_123",
                    "qualified_name": "src.main.process",
                    "type": "Function",
                    "path": "src/main.py",
                    "name": "process"
                }
            })
            
            context = await service.get_context("node_123")
            
            assert context.entity_id == "node_123"
            assert context.qualified_name == "src.main.process"
            assert context.entity_type == "Function"
            assert context.file_path == "src/main.py"
            assert context.repository_id == repo_id
            assert context.snapshot_id == snapshot_id

@pytest.mark.asyncio
async def test_get_context_not_found(mock_db, repo_id, snapshot_id):
    service = InvestigationService(mock_db, repo_id)
    
    with patch.object(service, '_resolve_snapshot_id', return_value=snapshot_id):
        with patch('archon.services.investigation_service.GraphService') as mock_graph_class:
            mock_graph = mock_graph_class.return_value
            mock_graph.get_node_details = AsyncMock(return_value={})
            
            with pytest.raises(HTTPException) as exc:
                await service.get_context("node_123")
                
            assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_get_code_success(mock_db, repo_id, snapshot_id):
    service = InvestigationService(mock_db, repo_id)
    
    context = InvestigationContext(
        repository_id=repo_id,
        snapshot_id=snapshot_id,
        entity_id="123",
        entity_name="process",
        entity_type="Function",
        file_path="main.py"
    )
    
    with patch('archon.services.investigation_service.RepositoryStorageService') as mock_storage_class:
        mock_storage = mock_storage_class.return_value
        mock_storage.get_file.return_value = "def process():\n    return 1"
        
        # In __init__, storage is created, so let's patch the instance
        service.storage = mock_storage
        
        with patch('archon.services.investigation_service._extract_ast_node', return_value="def process():\n    return 1"):
            code_ctx = await service.get_code(context)
            assert code_ctx is not None
            assert "def process" in code_ctx.source_code
            assert not code_ctx.truncated

@pytest.mark.asyncio
async def test_get_impact_null_lookup(mock_db, repo_id, snapshot_id):
    service = InvestigationService(mock_db, repo_id)
    
    context = InvestigationContext(
        repository_id=repo_id,
        snapshot_id=snapshot_id,
        entity_id="123",
        entity_name="process",
        entity_type="Unknown",
        file_path=None,
        qualified_name=None
    )
    
    with patch("archon.services.investigation_service.ImpactService") as mock_impact_cls:
        mock_impact_inst = mock_impact_cls.return_value
        mock_impact_inst.analyze = AsyncMock(side_effect=ValueError("Entity not found"))
        impact = await service.get_impact(context)
        assert impact.direct_callers == 0
        assert impact.graph["nodes"] == []
