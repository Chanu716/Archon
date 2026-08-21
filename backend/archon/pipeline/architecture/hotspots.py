"""
Dependency Hotspot Analyzer (Slice ML-11)

Identifies central architectural bottlenecks based on graph topology metrics:
  - In-degree (fan-in): number of distinct components depending on this node
  - Out-degree (fan-out): number of distinct components this node depends on
  - Transitive dependents count
  - Repository-relative percentile calculation
  - Deterministic and explainable severity scoring
"""

from typing import List, Dict, Set, Tuple
import structlog

from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import HotspotFact, ArchitectureNodeFact

logger = structlog.get_logger(__name__)


class HotspotAnalyzer:
    """
    Computes graph topology metrics to surface architectural hotspots.
    """

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

    def analyze_hotspots(
        self,
        node_facts: Dict[str, ArchitectureNodeFact],
        resolved_facts: List[ResolutionResult]
    ) -> List[HotspotFact]:
        # 1. Build directed graph adjacency
        incoming_edges: Dict[str, Set[str]] = {}
        outgoing_edges: Dict[str, Set[str]] = {}

        for rel in resolved_facts:
            if rel.relationship in ("CALLS", "DEPENDS_ON", "REQUESTS", "IMPORTS") and rel.resolution in ("exact", "inferred"):
                u, v = rel.source_id, rel.target_id
                if u != v:
                    outgoing_edges.setdefault(u, set()).add(v)
                    incoming_edges.setdefault(v, set()).add(u)

        all_nodes = sorted(set(node_facts.keys()) | set(incoming_edges.keys()) | set(outgoing_edges.keys()))
        if not all_nodes:
            return []

        # 2. Compute fan-in and fan-out counts
        fan_in_map: Dict[str, int] = {node: len(incoming_edges.get(node, set())) for node in all_nodes}
        fan_out_map: Dict[str, int] = {node: len(outgoing_edges.get(node, set())) for node in all_nodes}

        # 3. Compute transitive dependents count (bounded DFS)
        transitive_dependents_map: Dict[str, int] = {}
        for node in all_nodes:
            visited: Set[str] = set()
            stack = list(incoming_edges.get(node, set()))
            while stack:
                curr = stack.pop()
                if curr not in visited and curr != node:
                    visited.add(curr)
                    stack.extend(incoming_edges.get(curr, set()) - visited)
            transitive_dependents_map[node] = len(visited)

        # 4. Compute percentiles
        all_fan_ins = sorted(fan_in_map.values())
        total_nodes = len(all_fan_ins)

        hotspots: List[HotspotFact] = []

        for node in all_nodes:
            fan_in = fan_in_map[node]
            fan_out = fan_out_map[node]
            trans_dep = transitive_dependents_map[node]

            # Calculate percentile rank
            rank = sum(1 for x in all_fan_ins if x <= fan_in)
            percentile = (rank / total_nodes) * 100.0 if total_nodes > 0 else 0.0

            # Determine severity based on fan-in and percentile
            if fan_in >= 5 or (fan_in >= 3 and percentile >= 85.0):
                severity = "high"
            elif fan_in >= 2 or percentile >= 70.0:
                severity = "medium"
            else:
                severity = "low"

            node_fact = node_facts.get(node)
            node_kind = node_fact.node_kind if node_fact else "Node"

            explanation = (
                f"{severity.capitalize()} architectural hotspot: {fan_in} direct dependents and "
                f"{trans_dep} transitive dependents (top {100.0 - percentile:.1f}% percentile in repository)."
            )

            # We report nodes that have at least 2 dependents or are in medium/high severity
            if fan_in >= 2 or severity in ("medium", "high"):
                hotspots.append(HotspotFact(
                    qualified_name=node,
                    node_kind=node_kind,
                    fan_in=fan_in,
                    fan_out=fan_out,
                    transitive_dependents=trans_dep,
                    percentile=percentile,
                    severity=severity,
                    explanation=explanation,
                    repository_id=self.repository_id,
                    snapshot_id=self.snapshot_id
                ))

        # Sort descending by fan_in then transitive_dependents
        hotspots.sort(key=lambda x: (x.fan_in, x.transitive_dependents), reverse=True)
        logger.info(
            "hotspot_analysis_complete",
            hotspot_count=len(hotspots),
            snapshot_id=self.snapshot_id
        )
        return hotspots
