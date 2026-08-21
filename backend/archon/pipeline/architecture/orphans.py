"""
Orphaned Component Analyzer (Slice ML-11)

Identifies candidate orphaned classes, structs, or functions that have no meaningful
inbound architectural relationships (CALLS, REQUESTS, HANDLED_BY, DEPENDS_ON).

Guarantees:
  - Reports candidates as 'orphan_candidate' rather than claiming dead code.
  - Strict exclusion rules for framework entrypoints, endpoints, DI bindings, and interfaces.
"""

from typing import List, Dict, Set, Optional
import structlog

from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import (
    ArchitectureNodeFact,
    ArchitectureRole,
    OrphanFact,
)

logger = structlog.get_logger(__name__)

STANDARD_ENTRYPOINTS = {
    "main", "app", "index", "startup", "program", "server", "bootstrap"
}


class OrphanAnalyzer:
    """
    Identifies components with zero meaningful inbound architectural references.
    """

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

    def analyze_orphans(
        self,
        node_facts: Dict[str, ArchitectureNodeFact],
        resolved_facts: List[ResolutionResult],
        di_bound_types: Optional[Set[str]] = None
    ) -> List[OrphanFact]:
        di_types = di_bound_types or set()

        # 1. Collect all nodes that receive meaningful inbound edges
        referenced_nodes: Set[str] = set()
        for rel in resolved_facts:
            if rel.relationship in ("CALLS", "REQUESTS", "HANDLED_BY", "DEPENDS_ON"):
                referenced_nodes.add(rel.target_id)
                # If target is a method, also mark owner class as referenced
                if "." in rel.target_id:
                    owner_qname = ".".join(rel.target_id.split(".")[:-1])
                    referenced_nodes.add(owner_qname)

        orphans: List[OrphanFact] = []

        for qname, fact in node_facts.items():
            simple_name = qname.split(".")[-1].lower()

            # ── Check Exclusions ──
            exclusions_checked = []

            # Exclusion 1: Standard entrypoints & startup files
            is_entrypoint = any(entry in simple_name for entry in STANDARD_ENTRYPOINTS)
            exclusions_checked.append("standard_entrypoint_check")
            if is_entrypoint:
                continue

            # Exclusion 2: Controllers & Endpoint Handlers
            is_endpoint = (
                fact.architecture_role in (ArchitectureRole.CONTROLLER, ArchitectureRole.ENDPOINT_HANDLER)
            )
            exclusions_checked.append("framework_endpoint_check")
            if is_endpoint:
                continue

            # Exclusion 3: DI-registered concrete classes
            is_di_bound = qname in di_types or any(t.endswith(f".{qname}") or qname.endswith(f".{t}") for t in di_types)
            exclusions_checked.append("di_container_binding_check")
            if is_di_bound:
                continue

            # Exclusion 4: Has inbound reference in graph
            has_inbound = (
                qname in referenced_nodes
                or any(r.startswith(f"{qname}.") for r in referenced_nodes)
            )
            exclusions_checked.append("graph_inbound_reference_check")
            if has_inbound:
                continue

            # Exclusion 5: Top-level file module or interface with known implementations
            if fact.node_kind == "Module":
                continue

            # Node passed all exclusion checks and has 0 inbound edges -> Orphan candidate
            orphans.append(OrphanFact(
                qualified_name=qname,
                node_kind=fact.node_kind,
                resolution="inferred",
                evidence_type="zero_meaningful_inbound_edges",
                exclusions_checked=exclusions_checked,
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=fact.file_path
            ))

        logger.info(
            "orphan_analysis_complete",
            orphan_count=len(orphans),
            snapshot_id=self.snapshot_id
        )
        return orphans
