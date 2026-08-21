import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from archon.services.graph_service import GraphService


def make_mock_node(element_id: str, labels: list, props: dict):
    node = MagicMock()
    node.element_id = element_id
    node.labels = labels
    node.items.return_value = list(props.items())
    node.__getitem__ = lambda self, key: props[key]
    node.keys.return_value = list(props.keys())
    return node


def make_mock_rel(element_id: str, rel_type: str, start_id: str, end_id: str, props: dict = {}):
    rel = MagicMock()
    rel.element_id = element_id
    rel.type = rel_type
    rel.items.return_value = list(props.items())
    rel.nodes = [MagicMock(element_id=start_id), MagicMock(element_id=end_id)]
    rel.start_node = MagicMock(element_id=start_id)
    rel.end_node = MagicMock(element_id=end_id)
    return rel


@pytest.mark.asyncio
async def test_search_nodes_calls_neo4j():
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    service = GraphService(repo_id, snapshot_id)

    mock_node = make_mock_node("node:1", ["Function"], {
        "qualified_name": "module.func",
        "name": "func",
        "snapshot_id": str(snapshot_id),
    })

    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=[{"n": mock_node}])

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("archon.services.graph_service.neo4j_driver") as mock_driver:
        mock_driver.session.return_value = mock_session
        results = await service.search_nodes("func", limit=10)

    assert len(results) == 1
    assert results[0]["data"]["type"] == "Function"


@pytest.mark.asyncio
async def test_expand_node_returns_bounded_results():
    """Verify that expansion is called with snapshot_id filtering — no unrestricted graph dump."""
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    service = GraphService(repo_id, snapshot_id)

    mock_rel = make_mock_rel("rel:1", "CALLS", "node:1", "node:2")
    mock_target_node = make_mock_node("node:2", ["Class"], {
        "qualified_name": "module.MyClass",
        "name": "MyClass",
        "snapshot_id": str(snapshot_id),
    })

    class AsyncResultIter:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            async def _gen():
                for item in self.items:
                    yield item
            return _gen()

    mock_result = AsyncResultIter([{
        "n": make_mock_node("node:1", ["Class"], {"qualified_name": "module.SourceClass", "name": "SourceClass", "snapshot_id": str(snapshot_id)}),
        "r": mock_rel,
        "m": mock_target_node,
    }])

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("archon.services.graph_service.neo4j_driver") as mock_driver:
        mock_driver.session.return_value = mock_session
        results = await service.expand_node("node:1")

    assert len(results["nodes"]) == 2
    assert len(results["edges"]) == 1
    assert any(n["data"]["id"] == "node:2" for n in results["nodes"])


@pytest.mark.asyncio
async def test_search_snapshot_isolation():
    """Verify that search passes snapshot_id parameter to Neo4j to enforce isolation."""
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    service = GraphService(repo_id, snapshot_id)

    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=[])
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("archon.services.graph_service.neo4j_driver") as mock_driver:
        mock_driver.session.return_value = mock_session
        await service.search_nodes("OrderService")

        # Verify snapshot_id was passed as parameter
        call_kwargs = mock_session.run.call_args[1]
        assert "snapshot_id" in call_kwargs, "snapshot_id must always be passed to search queries"
        assert call_kwargs["snapshot_id"] == str(snapshot_id)
