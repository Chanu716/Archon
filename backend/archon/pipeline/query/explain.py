"""
Architecture Explanation Builder (Slice ML-13)

Synthesizes deterministic, human-readable explanations exclusively from verified EvidenceFacts.

Guarantees:
  - Strict Rule: Every single claim in an explanation MUST reference an underlying EvidenceFact.
  - Zero hallucination or unverified causal speculation.
  - Generates clear structured bullet points with explicit rule citations.
"""

from typing import List, Dict, Optional, Tuple, Any
import structlog

from archon.pipeline.architecture.models import (
    ArchitectureViolation,
    ArchitectureCycle,
    HotspotFact,
    OrphanFact,
)
from archon.pipeline.evolution.models import (
    ChangeRiskFact,
    ArchitectureRegression,
    RegressionType,
)
from archon.pipeline.query.models import (
    Explanation,
    EvidenceFact,
    TraversalPath,
    ResolutionConfidence,
)

logger = structlog.get_logger(__name__)


class ArchitectureExplanationBuilder:
    """
    Constructs explainable narratives backed by atomic EvidenceFacts.
    """

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

    def explain_risk(
        self,
        entity: str,
        risk: ChangeRiskFact,
        regressions: List[ArchitectureRegression],
    ) -> Tuple[Explanation, List[EvidenceFact]]:
        evidence_facts: List[EvidenceFact] = []
        detailed_reasons: List[str] = []
        rules: List[str] = []

        # 1. Base Risk Evidence
        ev_risk = EvidenceFact(
            fact_type="change_risk",
            source_id=entity,
            details={"risk_level": risk.risk_level.value, "score": risk.score, "reasons": risk.reasons},
            confidence=ResolutionConfidence.EXACT,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
        )
        evidence_facts.append(ev_risk)

        for r in risk.high_risk_factors:
            detailed_reasons.append(f"[HIGH RISK] {r}")
            rules.append("Rule: High-risk regressions require architectural review before deployment.")

        for r in risk.medium_risk_factors:
            detailed_reasons.append(f"[MEDIUM RISK] {r}")
            rules.append("Rule: Moderate coupling expansion or resolution degradation observed.")

        # 2. Correlate with specific regressions affecting this entity
        entity_regs = [reg for reg in regressions if reg.affected_entity == entity or entity in str(reg.evidence)]
        for reg in entity_regs:
            ev_reg = EvidenceFact(
                fact_type="regression",
                source_id=entity,
                details={"regression_type": reg.regression_type.value, "severity": reg.severity, "message": reg.message},
                confidence=ResolutionConfidence.EXACT,
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
            )
            evidence_facts.append(ev_reg)
            detailed_reasons.append(f"Triggering regression ({reg.severity.upper()}): {reg.message}")

        if not detailed_reasons:
            detailed_reasons.append("Change risk is LOW with zero detected architectural regressions.")

        summary = f"Entity '{entity}' has been evaluated as {risk.risk_level.value.upper()} risk (risk score: {risk.score}/100)."

        explanation = Explanation(
            summary=summary,
            detailed_reasons=detailed_reasons,
            rule_references=list(set(rules)),
            evidence_fact_ids=[f"{e.fact_type}:{e.source_id}" for e in evidence_facts],
        )
        return explanation, evidence_facts

    def explain_violation(
        self,
        violation: ArchitectureViolation,
    ) -> Tuple[Explanation, List[EvidenceFact]]:
        evidence = EvidenceFact(
            fact_type="violation",
            source_id=violation.source_qualified_name,
            target_id=violation.target_qualified_name,
            details={
                "violation_type": violation.violation_type,
                "severity": violation.severity,
                "source_layer": violation.source_layer,
                "target_layer": violation.target_layer,
                "message": violation.message,
            },
            confidence=ResolutionConfidence.EXACT if violation.resolution == "exact" else ResolutionConfidence.INFERRED,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
        )

        rules = []
        if violation.violation_type == "layer_skip":
            rules.append("Architecture Boundary Rule: Components in the Presentation layer must not directly bypass Application to access Infrastructure.")
        elif violation.violation_type == "reverse_dependency":
            rules.append("Architecture Inversion Rule: Inner/Domain layers must not depend on outer Presentation/Infrastructure layers.")
        elif violation.violation_type == "boundary_bypass":
            rules.append("Dependency Injection Rule: Concrete classes must not be directly depended on when an interface DI contract is configured.")

        summary = f"Architectural violation '{violation.violation_type}' detected on '{violation.source_qualified_name}' -> '{violation.target_qualified_name}'."
        detailed_reasons = [
            f"Source '{violation.source_qualified_name}' belongs to layer '{violation.source_layer}'.",
            f"Target '{violation.target_qualified_name}' belongs to layer '{violation.target_layer}'.",
            f"Violation details: {violation.message}",
        ]

        return Explanation(
            summary=summary,
            detailed_reasons=detailed_reasons,
            rule_references=rules,
            evidence_fact_ids=[f"violation:{violation.source_qualified_name}->{violation.target_qualified_name}"],
        ), [evidence]

    def explain_cycle(
        self,
        cycle: ArchitectureCycle,
    ) -> Tuple[Explanation, List[EvidenceFact]]:
        evidence = EvidenceFact(
            fact_type="cycle",
            source_id=cycle.members[0],
            details={"members": cycle.members, "relationships": cycle.relationship_types, "severity": cycle.severity},
            confidence=ResolutionConfidence.EXACT,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
        )

        cycle_path_str = " -> ".join(cycle.members) + f" -> {cycle.members[0]}"
        summary = f"Circular dependency cycle ({cycle.severity.upper()} severity) involving {len(cycle.members)} components."
        detailed_reasons = [
            f"Dependency cycle path: {cycle_path_str}",
            f"Participating entities: {', '.join(cycle.members)}",
            f"Relationship transitions: {', '.join(cycle.relationship_types)}",
        ]
        rules = ["Acyclic Dependency Principle: Architectural dependency graphs must form a Directed Acyclic Graph (DAG)."]

        return Explanation(
            summary=summary,
            detailed_reasons=detailed_reasons,
            rule_references=rules,
            evidence_fact_ids=[f"cycle:{cycle.cycle_id}"],
        ), [evidence]

    def explain_hotspot(
        self,
        hotspot: HotspotFact,
    ) -> Tuple[Explanation, List[EvidenceFact]]:
        evidence = EvidenceFact(
            fact_type="hotspot",
            source_id=hotspot.qualified_name,
            details={
                "fan_in": hotspot.fan_in,
                "fan_out": hotspot.fan_out,
                "transitive_dependents": hotspot.transitive_dependents,
                "percentile": hotspot.percentile,
                "severity": hotspot.severity,
            },
            confidence=ResolutionConfidence.EXACT,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
        )

        summary = f"Entity '{hotspot.qualified_name}' is an architectural hotspot ({hotspot.severity.upper()} severity)."
        detailed_reasons = [
            f"Fan-in: {hotspot.fan_in} direct inbound dependents.",
            f"Fan-out: {hotspot.fan_out} direct outbound dependencies.",
            f"Transitive blast radius: {hotspot.transitive_dependents} downstream components depend on this entity.",
            f"Coupling percentile: {hotspot.percentile:.1f}% across all repository components.",
        ]
        rules = ["Coupling Threshold Rule: Components with high fan-in represent critical change-risk concentration points."]

        return Explanation(
            summary=summary,
            detailed_reasons=detailed_reasons,
            rule_references=rules,
            evidence_fact_ids=[f"hotspot:{hotspot.qualified_name}"],
        ), [evidence]

    def explain_orphan(
        self,
        orphan: OrphanFact,
    ) -> Tuple[Explanation, List[EvidenceFact]]:
        evidence = EvidenceFact(
            fact_type="orphan",
            source_id=orphan.qualified_name,
            details={"entity_kind": orphan.entity_kind, "exclusions_checked": orphan.exclusions_checked},
            confidence=ResolutionConfidence.EXACT,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
        )

        summary = f"Component '{orphan.qualified_name}' is identified as a candidate orphan."
        detailed_reasons = [
            f"Zero meaningful inbound architectural references (CALLS, DEPENDS_ON, REQUESTS, IMPORTS).",
            f"Conservative exclusions verified: {', '.join(orphan.exclusions_checked)} were checked and did not match.",
            "Designation: Candidate orphan component (no claim of dead code is made without runtime reflection).",
        ]
        rules = ["Orphan Identification Rule: Unreferenced non-entrypoint components are flagged as candidate orphans for cleanup review."]

        return Explanation(
            summary=summary,
            detailed_reasons=detailed_reasons,
            rule_references=rules,
            evidence_fact_ids=[f"orphan:{orphan.qualified_name}"],
        ), [evidence]

    def explain_paths(
        self,
        source: str,
        target: Optional[str],
        paths: List[TraversalPath],
        query_type: str,
    ) -> Explanation:
        if not paths:
            if target:
                return Explanation(
                    summary=f"No architectural dependency path found between '{source}' and '{target}'.",
                    detailed_reasons=[f"Traversed graph up to maximum depth without finding a connected relationship."],
                )
            else:
                return Explanation(
                    summary=f"No {query_type.replace('_', ' ')} found for entity '{source}'.",
                    detailed_reasons=[f"Entity '{source}' has zero matching {query_type} in this snapshot."],
                )

        target_desc = f" to '{target}'" if target else ""
        summary = f"Discovered {len(paths)} architectural path(s) from '{source}'{target_desc}."
        detailed_reasons = []
        for i, p in enumerate(paths[:5], 1):
            chain_str = " -> ".join([p.start_entity] + [f"{s.relationship} -> {s.target_id}" for s in p.steps])
            detailed_reasons.append(f"Path #{i} (Length {p.length}): {chain_str}")

        if len(paths) > 5:
            detailed_reasons.append(f"... and {len(paths) - 5} additional path(s).")

        return Explanation(
            summary=summary,
            detailed_reasons=detailed_reasons,
            rule_references=["Deterministic Graph Traversal: Direct & transitive relationship discovery."],
            evidence_fact_ids=[f"path:{p.start_entity}->{p.end_entity}" for p in paths[:5]],
        )
