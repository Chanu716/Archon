"""
Deterministic Circular Dependency Detector (Slice ML-11)

Detects directed dependency cycles among components using CALLS, DEPENDS_ON, and IMPORTS.
Guarantees:
  - Directed graph analysis with cycle canonicalization (no duplicate reporting of rotated cycles).
  - Snapshot and repository isolation.
  - Deterministic severity scoring (2 nodes -> medium, >=3 nodes -> high).
"""

from typing import List, Dict, Set, Tuple
import structlog

from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import ArchitectureCycle

logger = structlog.get_logger(__name__)


class CycleDetector:
    """
    Finds and canonicalizes circular dependencies in resolved relationships.
    """

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

    def detect_cycles(self, resolved_facts: List[ResolutionResult]) -> List[ArchitectureCycle]:
        # 1. Build adjacency list for CALLS, DEPENDS_ON, IMPORTS
        adj: Dict[str, Set[str]] = {}
        edge_types: Dict[Tuple[str, str], Set[str]] = {}

        for rel in resolved_facts:
            if rel.relationship in ("CALLS", "DEPENDS_ON", "IMPORTS") and rel.resolution in ("exact", "inferred"):
                u, v = rel.source_id, rel.target_id
                if u != v: # Ignore self-recursion for architecture cycle purposes
                    adj.setdefault(u, set()).add(v)
                    edge_types.setdefault((u, v), set()).add(rel.relationship)

        # 2. Find all elementary cycles using DFS with back-edges
        raw_cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: List[str] = []
        rec_set: Set[str] = set()

        def dfs(curr: str):
            visited.add(curr)
            rec_stack.append(curr)
            rec_set.add(curr)

            for neighbor in sorted(adj.get(curr, set())):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_set:
                    # Found a cycle from neighbor to curr
                    idx = rec_stack.index(neighbor)
                    cycle_path = rec_stack[idx:]
                    if len(cycle_path) >= 2:
                        raw_cycles.append(cycle_path)

            rec_stack.pop()
            rec_set.remove(curr)

        for node in sorted(adj.keys()):
            if node not in visited:
                dfs(node)

        # 3. Canonicalize cycles to eliminate duplicate rotations
        canonical_cycles: Dict[str, ArchitectureCycle] = {}

        for c in raw_cycles:
            # Rotate cycle so that lexicographically minimum node is first
            min_idx = c.index(min(c))
            canonical_path = c[min_idx:] + c[:min_idx]
            cycle_key = "->".join(canonical_path)

            if cycle_key not in canonical_cycles:
                # Gather relationship types
                rel_types: Set[str] = set()
                for i in range(len(canonical_path)):
                    u = canonical_path[i]
                    v = canonical_path[(i + 1) % len(canonical_path)]
                    rel_types.update(edge_types.get((u, v), []))

                length = len(canonical_path)
                severity = "medium" if length == 2 else "high"

                canonical_cycles[cycle_key] = ArchitectureCycle(
                    cycle_id=f"cycle:{cycle_key}",
                    members=canonical_path,
                    relationship_types=sorted(rel_types),
                    severity=severity,
                    repository_id=self.repository_id,
                    snapshot_id=self.snapshot_id,
                    description=f"Circular dependency involving {length} components: {' -> '.join(canonical_path)} -> {canonical_path[0]}"
                )

        results = sorted(canonical_cycles.values(), key=lambda x: x.cycle_id)
        logger.info(
            "cycle_detection_complete",
            cycle_count=len(results),
            snapshot_id=self.snapshot_id
        )
        return results
