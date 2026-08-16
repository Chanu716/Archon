"""
Impact Analysis Service

Deterministic graph traversal to answer: "What could be affected if I change X?"

Algorithm overview
──────────────────
We use BFS (breadth-first search) with a Python-level visited set.
Cycle detection is handled entirely in Python — we do NOT rely on Neo4j
path-length limits or APOC for termination guarantees.

Each BFS hop fires one parameterized Cypher query (bounded by LIMIT).
This gives us predictable performance and explicit control over limits.

Resolution confidence propagation
──────────────────────────────────
The worst resolution along a path is carried forward:
  exact → exact    (unchanged)
  exact → inferred → inferred (the path is now "inferred" quality)
  any   → unresolved → unresolved (but these are surfaced separately)

Unresolved calls are NOT added to the confirmed impact sets. They are
collected in `unresolved_references` on the ImpactResult.

Direction definitions
─────────────────────
  upstream  = callers  (entities that depend on the target)
  downstream = callees (entities the target depends on)
"""
import uuid
from collections import deque
from typing import List, Optional, Set, Dict, Tuple

import structlog

from archon.db.neo4j import neo4j_driver
from archon.models.impact import (
    ImpactedEntity, ImpactResult, ImpactSummary, TraversalMetadata,
)

logger = structlog.get_logger(__name__)

# Resolution ordering — lower is better/more confident
_RESOLUTION_RANK = {"exact": 0, "inferred": 1, "unresolved": 2}

def _weaker(a: str, b: str) -> str:
    """Returns the weaker (less confident) of two resolution strings."""
    return a if _RESOLUTION_RANK.get(a, 2) >= _RESOLUTION_RANK.get(b, 2) else b


class ImpactService:
    def __init__(
        self,
        repository_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        max_depth: int = 5,
        max_nodes: int = 500,
    ):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)
        self.max_depth = max_depth
        self.max_nodes = max_nodes

    # ── Public API ────────────────────────────────────────────────────────────

    async def analyze(
        self,
        entity_id: str,
        direction: str = "both",
    ) -> ImpactResult:
        """
        Run impact analysis for the given entity.

        direction: 'upstream' | 'downstream' | 'both'
        """
        # Fetch target node metadata
        target = await self._get_node(entity_id)
        if not target:
            raise ValueError(f"Entity {entity_id} not found in snapshot {self.snapshot_id}")

        result = ImpactResult(
            target_id=entity_id,
            target_name=target.get("name") or target.get("qualified_name") or entity_id,
            target_type=target.get("type", "Unknown"),
            snapshot_id=self.snapshot_id,
        )

        nodes_visited = 0
        actual_depth = 0
        truncated = False

        if direction in ("upstream", "both"):
            callers_direct, callers_indirect, unresolved_up, depth_up, visited_up = \
                await self._bfs(entity_id, direction="upstream")
            result.direct_callers = callers_direct
            result.indirect_callers = callers_indirect
            result.unresolved_references.extend(unresolved_up)
            nodes_visited += len(visited_up)
            actual_depth = max(actual_depth, depth_up)
            if len(visited_up) >= self.max_nodes:
                truncated = True

        if direction in ("downstream", "both"):
            callees_direct, callees_indirect, unresolved_down, depth_down, visited_down = \
                await self._bfs(entity_id, direction="downstream")
            result.direct_callees = callees_direct
            result.indirect_callees = callees_indirect
            result.unresolved_references.extend(unresolved_down)
            nodes_visited += len(visited_down)
            actual_depth = max(actual_depth, depth_down)
            if len(visited_down) >= self.max_nodes:
                truncated = True

        # Deduplicate unresolved references
        seen_unres: Set[str] = set()
        deduped_unresolved = []
        for u in result.unresolved_references:
            if u.id not in seen_unres:
                seen_unres.add(u.id)
                deduped_unresolved.append(u)
        result.unresolved_references = deduped_unresolved

        # Translate all impacted entities to file/module/class containers
        all_impacted_ids = [e.id for e in
            result.direct_callers + result.indirect_callers +
            result.direct_callees + result.indirect_callees]
        
        files, modules, classes = await self._get_containers(all_impacted_ids)
        result.affected_files = files
        result.affected_modules = modules
        result.affected_classes = classes

        # Build summary
        result.summary = ImpactSummary(
            direct_callers=len(result.direct_callers),
            indirect_callers=len(result.indirect_callers),
            direct_callees=len(result.direct_callees),
            indirect_callees=len(result.indirect_callees),
            affected_files=len(result.affected_files),
            affected_modules=len(result.affected_modules),
            affected_classes=len(result.affected_classes),
            unresolved_references=len(result.unresolved_references),
        )

        result.traversal = TraversalMetadata(
            max_depth=self.max_depth,
            max_nodes=self.max_nodes,
            actual_depth_reached=actual_depth,
            nodes_visited=nodes_visited,
            truncated=truncated,
        )

        logger.info(
            "impact_analysis_complete",
            target=result.target_name,
            direction=direction,
            **{k: v for k, v in result.summary.__dict__.items()},
            truncated=truncated,
        )
        return result

    # ── BFS Traversal ─────────────────────────────────────────────────────────

    async def _bfs(
        self,
        start_id: str,
        direction: str,
    ) -> Tuple[List[ImpactedEntity], List[ImpactedEntity], List[ImpactedEntity], int, Set[str]]:
        """
        BFS traversal in one direction.

        Returns: (direct, indirect, unresolved, max_depth_reached, visited_set)
        """
        direct: List[ImpactedEntity] = []
        indirect: List[ImpactedEntity] = []
        unresolved: List[ImpactedEntity] = []

        visited: Set[str] = {start_id}
        # Queue items: (node_id, distance, path_so_far, cumulative_resolution)
        queue: deque = deque([(start_id, 0, [], "exact")])
        max_depth_reached = 0

        while queue:
            if len(visited) >= self.max_nodes:
                break

            current_id, depth, path, cumulative_resolution = queue.popleft()

            if depth >= self.max_depth:
                continue

            neighbors = await self._get_neighbors(current_id, direction)

            for neighbor in neighbors:
                neighbor_id = neighbor["id"]
                edge_resolution = neighbor.get("resolution", "exact")

                # Propagate the weakest resolution along the path
                path_resolution = _weaker(cumulative_resolution, edge_resolution)

                if neighbor_id in visited:
                    continue

                visited.add(neighbor_id)
                max_depth_reached = max(max_depth_reached, depth + 1)

                entity_path = path + [neighbor.get("name", neighbor_id)]

                entity = ImpactedEntity(
                    id=neighbor_id,
                    type=neighbor.get("type", "Unknown"),
                    name=neighbor.get("name") or neighbor.get("qualified_name") or neighbor_id,
                    qualified_name=neighbor.get("qualified_name"),
                    file=neighbor.get("file"),
                    distance=depth + 1,
                    relationship="CALLS",
                    resolution=path_resolution,
                    path=entity_path,
                )

                if edge_resolution == "unresolved":
                    # Unresolved → surfaced separately, not in confirmed impact
                    unresolved.append(entity)
                elif depth + 1 == 1:
                    direct.append(entity)
                else:
                    indirect.append(entity)

                # Only enqueue confirmed (exact/inferred) entities for further traversal
                if edge_resolution != "unresolved":
                    queue.append((neighbor_id, depth + 1, entity_path, path_resolution))

        return direct, indirect, unresolved, max_depth_reached, visited

    # ── Neo4j Queries ─────────────────────────────────────────────────────────

    async def _get_node(self, node_id: str) -> Optional[Dict]:
        """Fetches a single node's properties."""
        query = """
        MATCH (n {snapshot_id: $snapshot_id})
        WHERE elementId(n) = $node_id
        RETURN n.name AS name, n.qualified_name AS qualified_name,
               labels(n)[0] AS type
        """
        async with neo4j_driver.driver.session() as session:
            result = await session.run(query, snapshot_id=self.snapshot_id, node_id=node_id)
            record = await result.single()
            if not record:
                return None
            return dict(record)

    async def _get_neighbors(self, node_id: str, direction: str) -> List[Dict]:
        """
        Fetches 1-hop neighbors in the specified direction.

        upstream   = callers  → (caller)-[:CALLS]->(node)
        downstream = callees  → (node)-[:CALLS]->(callee)

        Only traverses CALLS relationships. CONTAINS/IMPORTS are handled
        separately for file/module translation.
        """
        if direction == "upstream":
            query = """
            MATCH (caller {snapshot_id: $snapshot_id})-[r:CALLS]->(n {snapshot_id: $snapshot_id})
            WHERE elementId(n) = $node_id
            RETURN elementId(caller) AS id,
                   caller.name AS name,
                   caller.qualified_name AS qualified_name,
                   labels(caller)[0] AS type,
                   r.resolution AS resolution
            LIMIT $limit
            """
        else:
            query = """
            MATCH (n {snapshot_id: $snapshot_id})-[r:CALLS]->(callee {snapshot_id: $snapshot_id})
            WHERE elementId(n) = $node_id
            RETURN elementId(callee) AS id,
                   callee.name AS name,
                   callee.qualified_name AS qualified_name,
                   labels(callee)[0] AS type,
                   r.resolution AS resolution
            LIMIT $limit
            """
        async with neo4j_driver.driver.session() as session:
            result = await session.run(
                query,
                snapshot_id=self.snapshot_id,
                node_id=node_id,
                limit=min(self.max_nodes, 200),
            )
            return await result.data()

    async def _get_containers(
        self, entity_ids: List[str]
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Translates impacted entity IDs into their containing File, Module, and Class nodes.
        Uses the CONTAINS / DEFINED_IN relationships already present in the graph.
        """
        if not entity_ids:
            return [], [], []

        query = """
        UNWIND $ids AS eid
        MATCH (n {snapshot_id: $snapshot_id})
        WHERE elementId(n) = eid
        OPTIONAL MATCH (f:File {snapshot_id: $snapshot_id})-[:CONTAINS]->(n)
        OPTIONAL MATCH (m:Module {snapshot_id: $snapshot_id})-[:CONTAINS]->(n)
        OPTIONAL MATCH (c:Class {snapshot_id: $snapshot_id})-[:CONTAINS]->(n)
        RETURN DISTINCT
            f.path AS file,
            m.qualified_name AS module,
            c.qualified_name AS class_name
        """
        async with neo4j_driver.driver.session() as session:
            result = await session.run(
                query, ids=entity_ids, snapshot_id=self.snapshot_id
            )
            records = await result.data()

        files = sorted({r["file"] for r in records if r.get("file")})
        modules = sorted({r["module"] for r in records if r.get("module")})
        classes = sorted({r["class_name"] for r in records if r.get("class_name")})
        return files, modules, classes
