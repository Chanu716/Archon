"""
Architecture Traversal Engine (Slice ML-13)

Executes bounded, cycle-safe, deterministic architectural graph traversals:
  - Upstream (inbound dependents)
  - Downstream (outbound dependencies)
  - Bidirectional traversal

Guarantees:
  - Strict depth bounding (default MAX_QUERY_DEPTH = 5).
  - Cycle safety via visited path tracking.
  - Deterministic sorting by qualified name and relationship type.
  - Generates auditable EvidenceFacts for every traversed relationship step.
"""

from typing import List, Dict, Set, Optional, Tuple
import structlog

from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.query.models import (
    TraversalPath,
    PathStep,
    EvidenceFact,
    ResolutionConfidence,
)

logger = structlog.get_logger(__name__)

DEFAULT_MAX_DEPTH = 5
SUPPORTED_RELATIONSHIPS = {
    "CALLS",
    "IMPORTS",
    "REQUESTS",
    "HANDLED_BY",
    "DEPENDS_ON",
    "IMPLEMENTS",
    "ARCHITECTURE_VIOLATION",
}


class ArchitectureTraversalEngine:
    """
    Traverses architectural graphs upstream or downstream with deterministic guarantees.
    """

    def __init__(self, repository_id: str, snapshot_id: str, max_depth: int = DEFAULT_MAX_DEPTH):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)
        self.max_depth = max_depth

    def traverse(
        self,
        start_entity: str,
        direction: str,  # "upstream" | "downstream" | "both"
        relationships: List[SnapshotRelationshipFact],
        entities: Dict[str, SnapshotEntityFact],
        allowed_rel_types: Optional[Set[str]] = None,
        max_depth: Optional[int] = None,
    ) -> Tuple[List[TraversalPath], List[EvidenceFact]]:
        limit_depth = max_depth if max_depth is not None else self.max_depth
        rel_filter = allowed_rel_types if allowed_rel_types else SUPPORTED_RELATIONSHIPS

        # Build adjacency maps
        # outbound: u -> [(rel_type, v, fact)]
        # inbound:  v -> [(rel_type, u, fact)]
        outbound: Dict[str, List[Tuple[str, str, SnapshotRelationshipFact]]] = {}
        inbound: Dict[str, List[Tuple[str, str, SnapshotRelationshipFact]]] = {}

        for r in relationships:
            if r.relationship_type in rel_filter:
                outbound.setdefault(r.source_id, []).append((r.relationship_type, r.target_id, r))
                inbound.setdefault(r.target_id, []).append((r.relationship_type, r.source_id, r))

        # Sort adjacencies for deterministic traversal
        for u in outbound:
            outbound[u].sort(key=lambda x: (x[0], x[1]))
        for v in inbound:
            inbound[v].sort(key=lambda x: (x[0], x[1]))

        paths: List[TraversalPath] = []
        evidence_facts: List[EvidenceFact] = []
        collected_evidence_ids: Set[str] = set()

        if direction in ("downstream", "both"):
            down_paths = self._traverse_dfs(
                current_node=start_entity,
                adj=outbound,
                entities=entities,
                is_downstream=True,
                current_path=[],
                visited_nodes={start_entity},
                max_depth=limit_depth,
                collected_evidence=evidence_facts,
                evidence_ids=collected_evidence_ids,
            )
            paths.extend(down_paths)

        if direction in ("upstream", "both"):
            up_paths = self._traverse_dfs(
                current_node=start_entity,
                adj=inbound,
                entities=entities,
                is_downstream=False,
                current_path=[],
                visited_nodes={start_entity},
                max_depth=limit_depth,
                collected_evidence=evidence_facts,
                evidence_ids=collected_evidence_ids,
            )
            paths.extend(up_paths)

        # Sort all paths deterministically
        paths.sort(key=lambda p: (p.length, p.end_entity, [s.relationship for s in p.steps]))
        evidence_facts.sort(key=lambda e: (e.fact_type, e.source_id, e.target_id or ""))

        return paths, evidence_facts

    def _traverse_dfs(
        self,
        current_node: str,
        adj: Dict[str, List[Tuple[str, str, SnapshotRelationshipFact]]],
        entities: Dict[str, SnapshotEntityFact],
        is_downstream: bool,
        current_path: List[PathStep],
        visited_nodes: Set[str],
        max_depth: int,
        collected_evidence: List[EvidenceFact],
        evidence_ids: Set[str],
    ) -> List[TraversalPath]:
        results: List[TraversalPath] = []

        if len(current_path) >= max_depth:
            return results

        neighbors = adj.get(current_node, [])
        for rel_type, next_node, rel_fact in neighbors:
            if next_node in visited_nodes:
                # Cycle prevention on active branch
                continue

            # Source and Target based on direction
            if is_downstream:
                src_id = current_node
                tgt_id = next_node
            else:
                src_id = next_node
                tgt_id = current_node

            src_fact = entities.get(src_id)
            tgt_fact = entities.get(tgt_id)

            step = PathStep(
                source_id=src_id,
                relationship=rel_type,
                target_id=tgt_id,
                source_role=src_fact.architecture_role if src_fact else None,
                target_role=tgt_fact.architecture_role if tgt_fact else None,
                source_layer=src_fact.architecture_layer if src_fact else None,
                target_layer=tgt_fact.architecture_layer if tgt_fact else None,
                resolution=rel_fact.resolution,
                evidence_type=rel_fact.evidence_type,
            )

            # Record atomic evidence fact
            ev_key = f"{src_id}->{rel_type}->{tgt_id}"
            if ev_key not in evidence_ids:
                evidence_ids.add(ev_key)
                collected_evidence.append(EvidenceFact(
                    fact_type="relationship",
                    source_id=src_id,
                    target_id=tgt_id,
                    relationship_type=rel_type,
                    details={
                        "resolution": rel_fact.resolution,
                        "evidence_type": rel_fact.evidence_type,
                        "source_role": step.source_role,
                        "target_role": step.target_role,
                    },
                    confidence=ResolutionConfidence.EXACT if rel_fact.resolution == "exact" else ResolutionConfidence.INFERRED,
                    repository_id=self.repository_id,
                    snapshot_id=self.snapshot_id,
                ))

            new_path_steps = current_path + [step]
            overall_conf = ResolutionConfidence.EXACT
            if any(s.resolution != "exact" for s in new_path_steps):
                overall_conf = ResolutionConfidence.INFERRED

            path_obj = TraversalPath(
                start_entity=new_path_steps[0].source_id if is_downstream else new_path_steps[-1].source_id,
                end_entity=next_node,
                steps=new_path_steps,
                length=len(new_path_steps),
                confidence=overall_conf,
            )
            results.append(path_obj)

            # Recurse
            sub_paths = self._traverse_dfs(
                current_node=next_node,
                adj=adj,
                entities=entities,
                is_downstream=is_downstream,
                current_path=new_path_steps,
                visited_nodes=visited_nodes | {next_node},
                max_depth=max_depth,
                collected_evidence=collected_evidence,
                evidence_ids=evidence_ids,
            )
            results.extend(sub_paths)

        return results
