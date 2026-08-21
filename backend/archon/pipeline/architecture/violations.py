"""
Architecture Violation Detector (Slice ML-11)

Detects deterministic architectural violations:
  1. layer_skip: e.g. presentation directly depending on infrastructure when an application layer exists
  2. reverse_dependency: e.g. domain depending on presentation or infrastructure
  3. boundary_bypass: direct dependency on concrete implementation when a proven interface + DI path exists
  4. circular_dependency: from CycleDetector
"""

from typing import List, Dict, Set, Optional
import structlog

from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import (
    ArchitectureNodeFact,
    ArchitectureLayer,
    ArchitectureViolation,
    ArchitectureCycle,
)
from archon.pipeline.architecture.boundaries import ArchitectureBoundaryAnalyzer, ALLOWED_TRANSITIONS

logger = structlog.get_logger(__name__)


class ArchitectureViolationAnalyzer:
    """
    Evaluates resolved edges and classifications to identify architectural rule violations.
    """

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)
        self.boundary_analyzer = ArchitectureBoundaryAnalyzer()

    def analyze_violations(
        self,
        node_facts: Dict[str, ArchitectureNodeFact],
        resolved_facts: List[ResolutionResult],
        cycles: List[ArchitectureCycle],
        di_bindings: Optional[Dict[str, str]] = None # iface -> concrete mapping
    ) -> List[ArchitectureViolation]:
        violations: List[ArchitectureViolation] = []
        emitted_keys: Set[str] = set()

        # Check if repository contains an active application / service layer
        has_application_layer = any(
            f.layer == ArchitectureLayer.APPLICATION for f in node_facts.values()
        )

        # 1. Analyze resolved CALLS and DEPENDS_ON edges for layer rules
        for rel in resolved_facts:
            if rel.relationship in ("CALLS", "DEPENDS_ON") and rel.resolution in ("exact", "inferred"):
                src_fact = node_facts.get(rel.source_id)
                tgt_fact = node_facts.get(rel.target_id)

                # Fallback: if caller is a method, check its owner class fact
                if not src_fact and "." in rel.source_id:
                    owner_qname = ".".join(rel.source_id.split(".")[:-1])
                    src_fact = node_facts.get(owner_qname)

                # If callee is a method, check its owner class fact
                if not tgt_fact and "." in rel.target_id:
                    owner_qname = ".".join(rel.target_id.split(".")[:-1])
                    tgt_fact = node_facts.get(owner_qname)

                if src_fact and tgt_fact:
                    src_layer = src_fact.layer
                    tgt_layer = tgt_fact.layer

                    if src_layer != ArchitectureLayer.UNKNOWN and tgt_layer != ArchitectureLayer.UNKNOWN:
                        # ── Violation Category A: Layer Skip ───────────────────
                        if (
                            src_layer == ArchitectureLayer.PRESENTATION
                            and tgt_layer == ArchitectureLayer.INFRASTRUCTURE
                        ):
                            if has_application_layer:
                                v_key = f"layer_skip:{src_fact.qualified_name}->{tgt_fact.qualified_name}"
                                if v_key not in emitted_keys:
                                    emitted_keys.add(v_key)
                                    violations.append(ArchitectureViolation(
                                        source_qualified_name=src_fact.qualified_name,
                                        target_qualified_name=tgt_fact.qualified_name,
                                        violation_type="layer_skip",
                                        severity="medium",
                                        resolution="exact",
                                        evidence_type="resolved_dependency_path",
                                        message=f"Presentation layer component '{src_fact.qualified_name}' directly bypasses application layer to access infrastructure '{tgt_fact.qualified_name}'",
                                        repository_id=self.repository_id,
                                        snapshot_id=self.snapshot_id,
                                        source_layer=src_layer.value,
                                        target_layer=tgt_layer.value
                                    ))

                        # ── Violation Category B: Reverse Dependency ──────────
                        elif (
                            src_layer == ArchitectureLayer.DOMAIN
                            and tgt_layer in (ArchitectureLayer.PRESENTATION, ArchitectureLayer.INFRASTRUCTURE)
                        ) or (
                            src_layer == ArchitectureLayer.INFRASTRUCTURE
                            and tgt_layer == ArchitectureLayer.PRESENTATION
                        ):
                            v_key = f"reverse_dep:{src_fact.qualified_name}->{tgt_fact.qualified_name}"
                            if v_key not in emitted_keys:
                                emitted_keys.add(v_key)
                                violations.append(ArchitectureViolation(
                                    source_qualified_name=src_fact.qualified_name,
                                    target_qualified_name=tgt_fact.qualified_name,
                                    violation_type="reverse_dependency",
                                    severity="high",
                                    resolution="exact",
                                    evidence_type="prohibited_layer_transition",
                                    message=f"Prohibited reverse dependency from {src_layer.value} layer '{src_fact.qualified_name}' to {tgt_layer.value} layer '{tgt_fact.qualified_name}'",
                                    repository_id=self.repository_id,
                                    snapshot_id=self.snapshot_id,
                                    source_layer=src_layer.value,
                                    target_layer=tgt_layer.value
                                ))

        # ── Violation Category C: Boundary Bypass ─────────────────────────────
        if di_bindings:
            for src_id, tgt_id in [(r.source_id, r.target_id) for r in resolved_facts if r.relationship in ("DEPENDS_ON", "CALLS")]:
                # If tgt_id is a concrete class for which an interface abstraction binding exists
                for iface, concrete in di_bindings.items():
                    if (tgt_id == concrete or tgt_id.endswith(f".{concrete}")) and not iface.endswith(tgt_id):
                        v_key = f"boundary_bypass:{src_id}->{tgt_id}"
                        if v_key not in emitted_keys:
                            emitted_keys.add(v_key)
                            violations.append(ArchitectureViolation(
                                source_qualified_name=src_id,
                                target_qualified_name=tgt_id,
                                violation_type="boundary_bypass",
                                severity="medium",
                                resolution="exact",
                                evidence_type="concrete_dependency_when_di_interface_exists",
                                message=f"Direct dependency on concrete implementation '{tgt_id}' when proven interface abstraction '{iface}' is registered in DI",
                                repository_id=self.repository_id,
                                snapshot_id=self.snapshot_id
                            ))

        # ── Violation Category D: Circular Dependency ─────────────────────────
        for c in cycles:
            v_key = f"cycle:{c.cycle_id}"
            if v_key not in emitted_keys:
                emitted_keys.add(v_key)
                violations.append(ArchitectureViolation(
                    source_qualified_name=c.members[0],
                    target_qualified_name=c.members[-1],
                    violation_type="circular_dependency",
                    severity=c.severity,
                    resolution="exact",
                    evidence_type="directed_graph_cycle",
                    message=c.description,
                    repository_id=self.repository_id,
                    snapshot_id=self.snapshot_id,
                    metadata={"cycle_members": c.members}
                ))

        logger.info(
            "architecture_violations_analyzed",
            total_violations=len(violations),
            layer_skips=sum(1 for v in violations if v.violation_type == "layer_skip"),
            reverse_deps=sum(1 for v in violations if v.violation_type == "reverse_dependency"),
            cycles=sum(1 for v in violations if v.violation_type == "circular_dependency"),
            boundary_bypasses=sum(1 for v in violations if v.violation_type == "boundary_bypass"),
            snapshot_id=self.snapshot_id
        )
        return violations
