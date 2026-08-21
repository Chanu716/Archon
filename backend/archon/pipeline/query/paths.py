"""
Dependency Path & HTTP Architecture Tracer (Slice ML-13)

Discovers deterministic paths between components:
  1. General Dependency Paths (Source -> ... -> Target)
  2. Complete HTTP Request Architecture Chains (UI -> Client -> Endpoint -> Handler -> Service -> Repo/DI)

Guarantees:
  - Depth-bounded (default MAX_QUERY_DEPTH = 5).
  - Cycle-safe traversal.
  - Zero speculative node additions.
  - Generates verifiable PathSteps and EvidenceFacts.
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

MAX_QUERY_DEPTH = 5
MAX_RETURNED_PATHS = 20
HTTP_CHAIN_RELATIONSHIPS = {"CALLS", "REQUESTS", "HANDLED_BY", "DEPENDS_ON", "IMPLEMENTS"}


class DependencyPathFinder:
    """
    Finds deterministic architectural paths between specific components or along HTTP request chains.
    """

    def __init__(self, repository_id: str, snapshot_id: str, max_depth: int = MAX_QUERY_DEPTH, max_paths: int = MAX_RETURNED_PATHS):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)
        self.max_depth = max_depth
        self.max_paths = max_paths

    def find_paths(
        self,
        source: str,
        target: str,
        relationships: List[SnapshotRelationshipFact],
        entities: Dict[str, SnapshotEntityFact],
        allowed_rel_types: Optional[Set[str]] = None,
        max_depth: Optional[int] = None,
    ) -> Tuple[List[TraversalPath], List[EvidenceFact], List[str]]:
        limit_depth = max_depth if max_depth is not None else self.max_depth
        warnings: List[str] = []

        if source == target:
            return [], [], ["Source and target entities are identical."]

        # Build adjacency
        outbound: Dict[str, List[Tuple[str, str, SnapshotRelationshipFact]]] = {}
        for r in relationships:
            if not allowed_rel_types or r.relationship_type in allowed_rel_types:
                outbound.setdefault(r.source_id, []).append((r.relationship_type, r.target_id, r))

        for u in outbound:
            outbound[u].sort(key=lambda x: (x[0], x[1]))

        found_paths: List[TraversalPath] = []
        evidence_facts: List[EvidenceFact] = []
        collected_evidence_ids: Set[str] = set()

        def dfs(curr: str, path: List[PathStep], visited: Set[str]):
            if len(found_paths) >= self.max_paths:
                return
            if len(path) >= limit_depth:
                return

            for rel_type, nxt, rel_fact in outbound.get(curr, []):
                if nxt in visited:
                    continue

                src_fact = entities.get(curr)
                tgt_fact = entities.get(nxt)

                step = PathStep(
                    source_id=curr,
                    relationship=rel_type,
                    target_id=nxt,
                    source_role=src_fact.architecture_role if src_fact else None,
                    target_role=tgt_fact.architecture_role if tgt_fact else None,
                    source_layer=src_fact.architecture_layer if src_fact else None,
                    target_layer=tgt_fact.architecture_layer if tgt_fact else None,
                    resolution=rel_fact.resolution,
                    evidence_type=rel_fact.evidence_type,
                )

                ev_key = f"{curr}->{rel_type}->{nxt}"
                if ev_key not in collected_evidence_ids:
                    collected_evidence_ids.add(ev_key)
                    evidence_facts.append(EvidenceFact(
                        fact_type="relationship",
                        source_id=curr,
                        target_id=nxt,
                        relationship_type=rel_type,
                        details={"resolution": rel_fact.resolution, "evidence_type": rel_fact.evidence_type},
                        confidence=ResolutionConfidence.EXACT if rel_fact.resolution == "exact" else ResolutionConfidence.INFERRED,
                        repository_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                    ))

                new_path = path + [step]

                if nxt == target:
                    overall_conf = ResolutionConfidence.EXACT
                    if any(s.resolution != "exact" for s in new_path):
                        overall_conf = ResolutionConfidence.INFERRED

                    found_paths.append(TraversalPath(
                        start_entity=source,
                        end_entity=target,
                        steps=new_path,
                        length=len(new_path),
                        confidence=overall_conf,
                    ))
                else:
                    dfs(nxt, new_path, visited | {nxt})

        dfs(source, [], {source})

        if len(found_paths) >= self.max_paths:
            warnings.append(f"Paths search truncated at maximum limit of {self.max_paths} paths.")

        found_paths.sort(key=lambda p: (p.length, [s.target_id for s in p.steps]))
        evidence_facts.sort(key=lambda e: (e.fact_type, e.source_id, e.target_id or ""))

        return found_paths, evidence_facts, warnings

    def trace_http_architecture(
        self,
        start_entity: str,
        relationships: List[SnapshotRelationshipFact],
        entities: Dict[str, SnapshotEntityFact],
        max_depth: Optional[int] = None,
    ) -> Tuple[List[TraversalPath], List[EvidenceFact], List[str]]:
        """
        Traces full frontend-to-backend request execution paths.
        """
        limit_depth = max_depth if max_depth is not None else self.max_depth

        outbound: Dict[str, List[Tuple[str, str, SnapshotRelationshipFact]]] = {}
        for r in relationships:
            if r.relationship_type in HTTP_CHAIN_RELATIONSHIPS:
                outbound.setdefault(r.source_id, []).append((r.relationship_type, r.target_id, r))

        for u in outbound:
            outbound[u].sort(key=lambda x: (x[0], x[1]))

        found_chains: List[TraversalPath] = []
        evidence_facts: List[EvidenceFact] = []
        collected_evidence_ids: Set[str] = set()

        def dfs(curr: str, path: List[PathStep], visited: Set[str]):
            if len(found_chains) >= self.max_paths or len(path) >= limit_depth:
                return

            neighbors = outbound.get(curr, [])
            if not neighbors and len(path) >= 2:
                # Reached a leaf in the HTTP chain (e.g. Repository or Implementation)
                overall_conf = ResolutionConfidence.EXACT
                if any(s.resolution != "exact" for s in path):
                    overall_conf = ResolutionConfidence.INFERRED

                found_chains.append(TraversalPath(
                    start_entity=start_entity,
                    end_entity=curr,
                    steps=path,
                    length=len(path),
                    confidence=overall_conf,
                ))
                return

            for rel_type, nxt, rel_fact in neighbors:
                if nxt in visited:
                    continue

                src_fact = entities.get(curr)
                tgt_fact = entities.get(nxt)

                step = PathStep(
                    source_id=curr,
                    relationship=rel_type,
                    target_id=nxt,
                    source_role=src_fact.architecture_role if src_fact else None,
                    target_role=tgt_fact.architecture_role if tgt_fact else None,
                    source_layer=src_fact.architecture_layer if src_fact else None,
                    target_layer=tgt_fact.architecture_layer if tgt_fact else None,
                    resolution=rel_fact.resolution,
                    evidence_type=rel_fact.evidence_type,
                )

                ev_key = f"{curr}->{rel_type}->{nxt}"
                if ev_key not in collected_evidence_ids:
                    collected_evidence_ids.add(ev_key)
                    evidence_facts.append(EvidenceFact(
                        fact_type="relationship",
                        source_id=curr,
                        target_id=nxt,
                        relationship_type=rel_type,
                        details={"resolution": rel_fact.resolution, "evidence_type": rel_fact.evidence_type},
                        confidence=ResolutionConfidence.EXACT if rel_fact.resolution == "exact" else ResolutionConfidence.INFERRED,
                        repository_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                    ))

                dfs(nxt, path + [step], visited | {nxt})

        dfs(start_entity, [], {start_entity})

        found_chains.sort(key=lambda p: (p.length, p.end_entity))
        evidence_facts.sort(key=lambda e: (e.fact_type, e.source_id, e.target_id or ""))

        return found_chains, evidence_facts, []
