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
        mock_driver.driver.session.return_value = mock_session
        results = await service.search_nodes("func", limit=10)

    assert len(results) == 1
    assert results[0]["data"]["type"] == "Function"


@pytest.mark.asyncio
async def test_expand_node_returns_bounded_results():
    """Verify that expansion is called with snapshot_id filtering — no unrestricted graph dump."""
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    service = GraphService(repo_id, snapshot_id)

    # We just want to confirm snapshot_id is always injected into the query params
    call_args_list = []

    class AsyncIter:
        def __init__(self, items):
            self.items = items
        async def __aiter__(self):
            for i in self.items:
                yield i

    async def mock_run(query, **params):
        call_args_list.append(params)
        return AsyncIter([])

    mock_session = AsyncMock()
    mock_session.run = mock_run
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("archon.services.graph_service.neo4j_driver") as mock_driver:
        mock_driver.driver.session.return_value = mock_session
        await service.expand_node("node:42")

    assert len(call_args_list) == 1
    assert call_args_list[0]["snapshot_id"] == str(snapshot_id), \
        "snapshot_id must be injected into every graph query for snapshot isolation"


@pytest.mark.asyncio
async def test_search_snapshot_isolation():
    """Every search query must be scoped to the correct snapshot_id."""
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    service = GraphService(repo_id, snapshot_id)

    call_args_list = []

    async def mock_run(query, **params):
        call_args_list.append(params)
        result = AsyncMock()
        result.data = AsyncMock(return_value=[])
        return result

    mock_session = AsyncMock()
    mock_session.run = mock_run
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("archon.services.graph_service.neo4j_driver") as mock_driver:
        mock_driver.driver.session.return_value = mock_session
        await service.search_nodes("SomeClass", limit=5)

    assert any(p.get("snapshot_id") == str(snapshot_id) for p in call_args_list), \
        "snapshot_id must always be passed to search queries"
