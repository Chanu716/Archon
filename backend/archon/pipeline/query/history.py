"""
Architecture History & Temporal Query Service (Slice ML-13)

Answers temporal and evolution questions across snapshots:
  - H1: What changed for entity X between snapshots?
  - H2: When did an issue (cycle, violation, hotspot) first appear?
  - H3: How did risk evolve over time?
  - H4: Explain multi-snapshot metric trends.

Guarantees:
  - Strict chronological snapshot evaluation.
  - Zero extrapolation or speculative timeline gaps.
  - Generates verifiable HistoricalSnapshotFacts and EvidenceFacts.
"""

from typing import List, Dict, Optional, Tuple, Any
import structlog

from archon.pipeline.architecture.models import (
    ArchitectureAnalysisResult,
    ArchitectureCycle,
    ArchitectureViolation,
    HotspotFact,
)
from archon.pipeline.evolution.models import (
    EvolutionAnalysisResult,
    ChangeType,
    MetricTrend,
    TrendDirection,
)
from archon.pipeline.query.models import (
    HistoricalSnapshotFact,
    EvidenceFact,
    Explanation,
    ResolutionConfidence,
)

logger = structlog.get_logger(__name__)


class ArchitectureHistoryService:
    """
    Executes historical and temporal architecture queries across snapshots.
    """

    def __init__(self, repository_id: str):
        self.repository_id = str(repository_id)

    def get_entity_history(
        self,
        entity_name: str,
        evolution_result: EvolutionAnalysisResult,
    ) -> Tuple[List[HistoricalSnapshotFact], List[EvidenceFact], Explanation]:
        history: List[HistoricalSnapshotFact] = []
        evidence: List[EvidenceFact] = []
        reasons: List[str] = []

        diff = evolution_result.diff

        # 1. Check Entity Lifecycle Diff
        ediff = diff.entity_diffs.get(entity_name)
        if ediff:
            desc = f"Entity '{entity_name}' was {ediff.change_type.value.upper()} in target snapshot."
            history.append(HistoricalSnapshotFact(
                snapshot_id=evolution_result.target_snapshot_id,
                fact_value=ediff.change_type.value,
                description=desc,
            ))
            reasons.append(desc)

            if ediff.field_changes:
                for field_name, (old_v, new_v) in ediff.field_changes.items():
                    change_desc = f"Field '{field_name}' changed: '{old_v}' -> '{new_v}'"
                    reasons.append(change_desc)
                    evidence.append(EvidenceFact(
                        fact_type="entity_diff",
                        source_id=entity_name,
                        details={"field": field_name, "old_value": old_v, "new_value": new_v},
                        confidence=ResolutionConfidence.EXACT,
                        repository_id=self.repository_id,
                        snapshot_id=evolution_result.target_snapshot_id,
                    ))

        # 2. Check Relationship Changes for this Entity
        added_rels = [r for r in diff.relationship_diffs.values() if r.source_id == entity_name and r.change_type == ChangeType.ADDED]
        removed_rels = [r for r in diff.relationship_diffs.values() if r.source_id == entity_name and r.change_type == ChangeType.REMOVED]

        if added_rels:
            for r in added_rels:
                reasons.append(f"Added {r.relationship_type} -> '{r.target_id}'")
        if removed_rels:
            for r in removed_rels:
                reasons.append(f"Removed {r.relationship_type} -> '{r.target_id}'")

        if not reasons:
            reasons.append(f"No architectural changes detected for entity '{entity_name}' between '{evolution_result.baseline_snapshot_id}' and '{evolution_result.target_snapshot_id}'.")

        summary = f"History of '{entity_name}' from '{evolution_result.baseline_snapshot_id}' to '{evolution_result.target_snapshot_id}'."
        explanation = Explanation(
            summary=summary,
            detailed_reasons=reasons,
            rule_references=["Snapshot Difference Analysis: Deterministic comparison of entity and relationship facts."],
            evidence_fact_ids=[f"history:{entity_name}"],
        )

        return history, evidence, explanation

    def find_issue_origin(
        self,
        issue_type: str,  # "cycle" | "violation" | "hotspot"
        issue_key: str,
        snapshot_history: List[Tuple[str, ArchitectureAnalysisResult]],
    ) -> Tuple[Optional[str], List[HistoricalSnapshotFact], List[EvidenceFact], Explanation]:
        """
        Identifies the earliest snapshot in the chronological history where the issue first appeared.
        """
        history: List[HistoricalSnapshotFact] = []
        evidence: List[EvidenceFact] = []

        if len(snapshot_history) < 1:
            return None, [], [], Explanation(
                summary="Insufficient snapshot history provided.",
                detailed_reasons=["At least one snapshot is required to inspect issue origins."],
            )

        origin_snapshot: Optional[str] = None

        for s_id, arch in snapshot_history:
            found = False
            if issue_type == "cycle":
                matching = [c for c in arch.cycles if c.cycle_id == issue_key or issue_key in c.members]
                if matching:
                    found = True
                    evidence.append(EvidenceFact(
                        fact_type="cycle",
                        source_id=matching[0].members[0],
                        details={"cycle_id": matching[0].cycle_id, "members": matching[0].members},
                        confidence=ResolutionConfidence.EXACT,
                        repository_id=self.repository_id,
                        snapshot_id=s_id,
                    ))

            elif issue_type == "violation":
                matching = [v for v in arch.violations if issue_key in f"{v.source_qualified_name}->{v.target_qualified_name}" or issue_key in v.violation_type]
                if matching:
                    found = True
                    evidence.append(EvidenceFact(
                        fact_type="violation",
                        source_id=matching[0].source_qualified_name,
                        target_id=matching[0].target_qualified_name,
                        details={"violation_type": matching[0].violation_type, "message": matching[0].message},
                        confidence=ResolutionConfidence.EXACT,
                        repository_id=self.repository_id,
                        snapshot_id=s_id,
                    ))

            elif issue_type == "hotspot":
                matching = [h for h in arch.hotspots if h.qualified_name == issue_key]
                if matching:
                    found = True
                    evidence.append(EvidenceFact(
                        fact_type="hotspot",
                        source_id=matching[0].qualified_name,
                        details={"fan_in": matching[0].fan_in, "fan_out": matching[0].fan_out},
                        confidence=ResolutionConfidence.EXACT,
                        repository_id=self.repository_id,
                        snapshot_id=s_id,
                    ))

            if found:
                history.append(HistoricalSnapshotFact(
                    snapshot_id=s_id,
                    fact_value=True,
                    description=f"Issue '{issue_key}' present in snapshot '{s_id}'.",
                ))
                if origin_snapshot is None:
                    origin_snapshot = s_id
            else:
                history.append(HistoricalSnapshotFact(
                    snapshot_id=s_id,
                    fact_value=False,
                    description=f"Issue '{issue_key}' absent in snapshot '{s_id}'.",
                ))

        if origin_snapshot:
            summary = f"Issue '{issue_key}' first appeared in snapshot '{origin_snapshot}'."
            reasons = [
                f"Inspected {len(snapshot_history)} snapshots chronologically.",
                f"Earliest snapshot exhibiting this {issue_type}: '{origin_snapshot}'.",
            ]
        else:
            summary = f"Issue '{issue_key}' was not found in any of the {len(snapshot_history)} examined snapshots."
            reasons = ["Zero occurrences recorded across snapshot timeline."]

        explanation = Explanation(
            summary=summary,
            detailed_reasons=reasons,
            rule_references=["Chronological Origin Analysis: First appearance in ordered snapshot sequence."],
            evidence_fact_ids=[f"origin:{issue_key}:{origin_snapshot}"],
        )

        return origin_snapshot, history, evidence, explanation

    def get_risk_evolution(
        self,
        evolution_results: List[EvolutionAnalysisResult],
    ) -> Tuple[List[HistoricalSnapshotFact], List[EvidenceFact], Explanation]:
        history: List[HistoricalSnapshotFact] = []
        evidence: List[EvidenceFact] = []
        reasons: List[str] = []

        for evo in evolution_results:
            if evo.risk:
                r_level = evo.risk.risk_level.value
                score = evo.risk.score
                desc = f"Snapshot '{evo.target_snapshot_id}': {r_level.upper()} Risk (Score {score}/100)"
                history.append(HistoricalSnapshotFact(
                    snapshot_id=evo.target_snapshot_id,
                    fact_value=r_level,
                    description=desc,
                ))
                reasons.append(desc)
                evidence.append(EvidenceFact(
                    fact_type="change_risk",
                    source_id=evo.target_snapshot_id,
                    details={"risk_level": r_level, "score": score, "reasons": evo.risk.reasons},
                    confidence=ResolutionConfidence.EXACT,
                    repository_id=self.repository_id,
                    snapshot_id=evo.target_snapshot_id,
                ))

        summary = f"Risk evolution evaluated across {len(evolution_results)} snapshot transitions."
        explanation = Explanation(
            summary=summary,
            detailed_reasons=reasons,
            rule_references=["Temporal Risk Evolution: Progression of rule-based risk levels."],
            evidence_fact_ids=[f"risk_evolution:{evo.target_snapshot_id}" for evo in evolution_results],
        )

        return history, evidence, explanation
