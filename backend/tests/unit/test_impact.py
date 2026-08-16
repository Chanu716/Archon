"""
Unit tests for the Impact Analysis Service.

All Neo4j calls are mocked — no live database required.

Tests cover:
  - Direct callers (A → Target)
  - Indirect callers (A → B → Target)
  - Downstream (Target → B → C)
  - Cycle termination (A → B → C → A)
  - Duplicate deduplication
  - Resolution confidence propagation
  - Traversal limits and truncated flag
  - Snapshot isolation (snapshot_id always injected)
  - Repository isolation (handled at API layer, tested separately)
"""
import pytest
import uuid
from collections import defaultdict
from unittest.mock import AsyncMock, patch, MagicMock
from archon.services.impact_service import ImpactService, _weaker


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_service(max_depth=5, max_nodes=500):
    return ImpactService(
        repository_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        max_depth=max_depth,
        max_nodes=max_nodes,
    )


def mock_neighbors(graph: dict):
    """
    Returns a mock _get_neighbors that uses a dict adjacency list:
      graph = { "nodeA": [{"id": "nodeB", "resolution": "exact", "name": "B", "type": "Function"}] }
    The direction parameter determines which key to look up.
    We store both upstream and downstream in the same graph dict,
    so tests must supply the correct direction view.
    """
    async def _mock_get_neighbors(node_id, direction):
        return graph.get(node_id, [])
    return _mock_get_neighbors


def mock_node(name="target", node_type="Function"):
    async def _get_node(node_id):
        return {"name": name, "qualified_name": f"mod.{name}", "type": node_type}
    return _get_node


def mock_containers():
    async def _get_containers(ids):
        return (
            [f"file_{i}.py" for i in range(len(ids))],
            [],
            [],
        )
    return _get_containers


# ── Resolution helper ─────────────────────────────────────────────────────────

def test_weaker_resolution():
    assert _weaker("exact", "exact") == "exact"
    assert _weaker("exact", "inferred") == "inferred"
    assert _weaker("inferred", "exact") == "inferred"
    assert _weaker("inferred", "unresolved") == "unresolved"
    assert _weaker("exact", "unresolved") == "unresolved"


# ── Direct callers ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_direct_callers():
    """A → Target: A should be a direct caller (distance=1)."""
    service = make_service()
    # upstream graph: for node "target", upstream neighbor is "A"
    upstream = {
        "target": [{"id": "A", "name": "caller_a", "qualified_name": "mod.caller_a", "type": "Function", "resolution": "exact"}]
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(upstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="upstream")

    assert len(result.direct_callers) == 1
    assert result.direct_callers[0].id == "A"
    assert result.direct_callers[0].distance == 1
    assert result.direct_callers[0].resolution == "exact"
    assert len(result.indirect_callers) == 0


# ── Indirect callers ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_indirect_callers():
    """A → B → Target: B=direct, A=indirect."""
    service = make_service()
    upstream = {
        "target": [{"id": "B", "name": "B", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "B":      [{"id": "A", "name": "A", "qualified_name": None, "type": "Function", "resolution": "exact"}],
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(upstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="upstream")

    direct_ids = {e.id for e in result.direct_callers}
    indirect_ids = {e.id for e in result.indirect_callers}

    assert "B" in direct_ids
    assert "A" in indirect_ids
    assert result.direct_callers[0].distance == 1
    assert result.indirect_callers[0].distance == 2


# ── Downstream ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_downstream_callees():
    """Target → B → C: B=direct callee, C=indirect callee."""
    service = make_service()
    downstream = {
        "target": [{"id": "B", "name": "B", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "B":      [{"id": "C", "name": "C", "qualified_name": None, "type": "Function", "resolution": "exact"}],
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(downstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="downstream")

    direct_ids = {e.id for e in result.direct_callees}
    indirect_ids = {e.id for e in result.indirect_callees}

    assert "B" in direct_ids
    assert "C" in indirect_ids


# ── Cycle termination ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cycle_terminates():
    """A → B → C → A must terminate without infinite loop."""
    service = make_service()
    # Upstream view: for each node, who calls it?
    # The cycle: target ← C ← B ← A ← C (cycle via A)
    upstream = {
        "target": [{"id": "C", "name": "C", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "C":      [{"id": "B", "name": "B", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "B":      [{"id": "A", "name": "A", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "A":      [{"id": "C", "name": "C", "qualified_name": None, "type": "Function", "resolution": "exact"}],  # cycle back
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(upstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="upstream")

    # Verify it completed (no infinite loop) and C, B, A were found
    all_ids = {e.id for e in result.direct_callers + result.indirect_callers}
    assert "C" in all_ids
    assert "B" in all_ids
    assert "A" in all_ids


# ── Deduplication ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_duplicate_entities():
    """Multiple paths to the same entity should yield only one entry."""
    service = make_service()
    # Both X and Y call target, and A calls both X and Y → A appears via two paths
    upstream = {
        "target": [
            {"id": "X", "name": "X", "qualified_name": None, "type": "Function", "resolution": "exact"},
            {"id": "Y", "name": "Y", "qualified_name": None, "type": "Function", "resolution": "exact"},
        ],
        "X": [{"id": "A", "name": "A", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "Y": [{"id": "A", "name": "A", "qualified_name": None, "type": "Function", "resolution": "exact"}],
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(upstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="upstream")

    all_ids = [e.id for e in result.direct_callers + result.indirect_callers]
    assert all_ids.count("A") == 1, f"A appeared {all_ids.count('A')} times, expected 1"


# ── Resolution propagation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolution_propagation():
    """exact → inferred path: terminal node should be 'inferred'."""
    service = make_service()
    upstream = {
        "target": [{"id": "B", "name": "B", "qualified_name": None, "type": "Function", "resolution": "inferred"}],
        "B":      [{"id": "A", "name": "A", "qualified_name": None, "type": "Function", "resolution": "exact"}],
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(upstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="upstream")

    b = next(e for e in result.direct_callers if e.id == "B")
    a = next(e for e in result.indirect_callers if e.id == "A")

    # B is direct with inferred resolution
    assert b.resolution == "inferred"
    # A is indirect — its path goes through an inferred edge, so it carries inferred
    assert a.resolution == "inferred"


@pytest.mark.asyncio
async def test_unresolved_not_in_confirmed_impact():
    """Unresolved calls must NOT appear in direct_callers or direct_callees."""
    service = make_service()
    upstream = {
        "target": [
            {"id": "B", "name": "B", "qualified_name": None, "type": "Function", "resolution": "exact"},
            {"id": "U", "name": "U", "qualified_name": None, "type": "Function", "resolution": "unresolved"},
        ],
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(upstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="upstream")

    confirmed_ids = {e.id for e in result.direct_callers + result.indirect_callers}
    assert "U" not in confirmed_ids, "Unresolved entity appeared in confirmed impact"
    unresolved_ids = {e.id for e in result.unresolved_references}
    assert "U" in unresolved_ids, "Unresolved entity missing from unresolved_references"


# ── Truncation ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_truncation_at_max_nodes():
    """Traversal should stop and report truncated=True when max_nodes is hit."""
    service = make_service(max_nodes=3)  # very small limit

    # Create a long chain: target ← N1 ← N2 ← N3 ← N4 (more than 3 nodes)
    upstream = {
        "target": [{"id": "N1", "name": "N1", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "N1": [{"id": "N2", "name": "N2", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "N2": [{"id": "N3", "name": "N3", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "N3": [{"id": "N4", "name": "N4", "qualified_name": None, "type": "Function", "resolution": "exact"}],
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(upstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="upstream")

    assert result.traversal.truncated is True


@pytest.mark.asyncio
async def test_depth_limit():
    """Traversal should not exceed max_depth."""
    service = make_service(max_depth=1)  # only direct neighbors

    upstream = {
        "target": [{"id": "B", "name": "B", "qualified_name": None, "type": "Function", "resolution": "exact"}],
        "B":      [{"id": "A", "name": "A", "qualified_name": None, "type": "Function", "resolution": "exact"}],
    }
    service._get_node = mock_node("target")
    service._get_neighbors = mock_neighbors(upstream)
    service._get_containers = mock_containers()

    result = await service.analyze("target", direction="upstream")

    all_ids = {e.id for e in result.direct_callers + result.indirect_callers}
    assert "B" in all_ids      # direct, within depth=1
    assert "A" not in all_ids  # indirect, beyond depth=1


# ── Snapshot isolation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_snapshot_id_always_injected():
    """Every Cypher query must pass snapshot_id — verified via mock call inspection."""
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    service = ImpactService(repo_id, snapshot_id, max_depth=2)

    observed_params = []

    async def mock_run(query, **params):
        observed_params.append(params)
        r = AsyncMock()
        r.single = AsyncMock(return_value=None)
        r.data = AsyncMock(return_value=[])
        r.__aiter__ = MagicMock(return_value=iter([]))
        return r

    mock_session = AsyncMock()
    mock_session.run = mock_run
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("archon.services.impact_service.neo4j_driver") as mock_driver:
        mock_driver.driver.session.return_value = mock_session
        # Expect ValueError because node won't be found; that's fine for this test
        try:
            await service.analyze("node:999", direction="upstream")
        except ValueError:
            pass

    for params in observed_params:
        assert params.get("snapshot_id") == str(snapshot_id), \
            f"snapshot_id missing from query params: {params}"
