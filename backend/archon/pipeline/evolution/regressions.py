"""
Architecture Regression Analyzer (Slice ML-12)

Identifies newly introduced architectural regressions between snapshots:
  - New Circular Dependencies (using canonical cycle identity)
  - New Architecture Rule Violations (layer skips, reverse dependencies, boundary bypasses)
  - Meaningful Hotspot Growth (fan-in / fan-out increase >= threshold)
  - Dependency Growth (material increase in outgoing dependencies)
  - Newly Orphaned Components (candidate orphans present in target but not baseline)
  - Resolution Regressions (exact edges degrading to inferred or unresolved)

Guarantees:
  - Existing problems in baseline are NEVER falsely flagged as new regressions.
  - Thresholds are configurable constants, not arbitrary magic numbers.
"""

from typing import List, Dict, Set, Optional, Tuple
import structlog

from archon.pipeline.evolution.models import (
    RegressionType,
    ArchitectureRegression,
    SnapshotDiffResult,
)
from archon.pipeline.architecture.models import (
    ArchitectureAnalysisResult,
    ArchitectureCycle,
    ArchitectureViolation,
    HotspotFact,
    OrphanFact,
)

logger = structlog.get_logger(__name__)

HOTSPOT_GROWTH_FAN_IN_DELTA = 2
HOTSPOT_GROWTH_FAN_OUT_DELTA = 2
DEPENDENCY_GROWTH_DELTA = 2


class ArchitectureRegressionAnalyzer:
    """
    Detects architectural regressions introduced in target snapshot compared to baseline snapshot.
    """

    def __init__(
        self,
        repository_id: str,
        baseline_snapshot_id: str,
        target_snapshot_id: str,
        hotspot_fan_in_threshold: int = HOTSPOT_GROWTH_FAN_IN_DELTA,
        hotspot_fan_out_threshold: int = HOTSPOT_GROWTH_FAN_OUT_DELTA,
        dependency_growth_threshold: int = DEPENDENCY_GROWTH_DELTA,
    ):
        self.repository_id = str(repository_id)
        self.baseline_snapshot_id = str(baseline_snapshot_id)
        self.target_snapshot_id = str(target_snapshot_id)
        self.hotspot_fan_in_threshold = hotspot_fan_in_threshold
        self.hotspot_fan_out_threshold = hotspot_fan_out_threshold
        self.dependency_growth_threshold = dependency_growth_threshold

    def analyze_regressions(
        self,
        diff: SnapshotDiffResult,
        baseline_arch: Optional[ArchitectureAnalysisResult],
        target_arch: Optional[ArchitectureAnalysisResult],
    ) -> List[ArchitectureRegression]:
        regressions: List[ArchitectureRegression] = []

        base_arch = baseline_arch or ArchitectureAnalysisResult()
        tgt_arch = target_arch or ArchitectureAnalysisResult()

        # ── 1. New Circular Dependencies ──────────────────────────────────────
        base_cycle_ids = {c.cycle_id for c in base_arch.cycles}
        for t_cycle in tgt_arch.cycles:
            if t_cycle.cycle_id not in base_cycle_ids:
                regressions.append(ArchitectureRegression(
                    regression_id=f"new_cycle:{t_cycle.cycle_id}",
                    regression_type=RegressionType.NEW_CYCLE,
                    severity=t_cycle.severity,
                    affected_entity=t_cycle.members[0],
                    message=f"Newly introduced circular dependency: {' -> '.join(t_cycle.members)} -> {t_cycle.members[0]}",
                    evidence={"cycle_members": t_cycle.members, "severity": t_cycle.severity},
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                ))

        # ── 2. New Architecture Violations ────────────────────────────────────
        base_violation_keys = {
            f"{v.violation_type}:{v.source_qualified_name}->{v.target_qualified_name}"
            for v in base_arch.violations
        }
        for t_viol in tgt_arch.violations:
            v_key = f"{t_viol.violation_type}:{t_viol.source_qualified_name}->{t_viol.target_qualified_name}"
            if v_key not in base_violation_keys:
                regressions.append(ArchitectureRegression(
                    regression_id=f"new_violation:{v_key}",
                    regression_type=RegressionType.NEW_ARCHITECTURE_VIOLATION,
                    severity=t_viol.severity,
                    affected_entity=t_viol.source_qualified_name,
                    message=f"Newly introduced {t_viol.violation_type} violation: {t_viol.message}",
                    evidence={
                        "violation_type": t_viol.violation_type,
                        "source": t_viol.source_qualified_name,
                        "target": t_viol.target_qualified_name,
                        "severity": t_viol.severity
                    },
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                ))

        # ── 3. Hotspot Growth ─────────────────────────────────────────────────
        base_hotspots: Dict[str, HotspotFact] = {h.qualified_name: h for h in base_arch.hotspots}
        for t_hotspot in tgt_arch.hotspots:
            b_hotspot = base_hotspots.get(t_hotspot.qualified_name)
            old_fan_in = b_hotspot.fan_in if b_hotspot else 0
            old_fan_out = b_hotspot.fan_out if b_hotspot else 0

            fan_in_delta = t_hotspot.fan_in - old_fan_in
            fan_out_delta = t_hotspot.fan_out - old_fan_out

            if fan_in_delta >= self.hotspot_fan_in_threshold or fan_out_delta >= self.hotspot_fan_out_threshold:
                regressions.append(ArchitectureRegression(
                    regression_id=f"hotspot_growth:{t_hotspot.qualified_name}",
                    regression_type=RegressionType.HOTSPOT_GROWTH,
                    severity="medium" if fan_in_delta < 5 else "high",
                    affected_entity=t_hotspot.qualified_name,
                    message=(
                        f"Architectural hotspot '{t_hotspot.qualified_name}' grew significantly: "
                        f"fan-in changed from {old_fan_in} to {t_hotspot.fan_in} (+{fan_in_delta}), "
                        f"fan-out changed from {old_fan_out} to {t_hotspot.fan_out} (+{fan_out_delta})."
                    ),
                    evidence={
                        "old_fan_in": old_fan_in,
                        "new_fan_in": t_hotspot.fan_in,
                        "fan_in_delta": fan_in_delta,
                        "old_fan_out": old_fan_out,
                        "new_fan_out": t_hotspot.fan_out,
                        "fan_out_delta": fan_out_delta,
                    },
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                ))

        # ── 4. Dependency Growth (Material increase in outgoing dependencies) ──
        base_deps_count: Dict[str, int] = {}
        tgt_deps_count: Dict[str, int] = {}

        for rdiff in diff.relationship_diffs.values():
            if rdiff.relationship_type in ("DEPENDS_ON", "CALLS"):
                if rdiff.baseline_rel:
                    base_deps_count[rdiff.source_id] = base_deps_count.get(rdiff.source_id, 0) + 1
                if rdiff.target_rel:
                    tgt_deps_count[rdiff.source_id] = tgt_deps_count.get(rdiff.source_id, 0) + 1

        for src_id, new_count in tgt_deps_count.items():
            old_count = base_deps_count.get(src_id, 0)
            delta = new_count - old_count
            if delta >= self.dependency_growth_threshold and old_count > 0:
                regressions.append(ArchitectureRegression(
                    regression_id=f"dependency_growth:{src_id}",
                    regression_type=RegressionType.DEPENDENCY_GROWTH,
                    severity="medium",
                    affected_entity=src_id,
                    message=f"Entity '{src_id}' increased its architectural coupling from {old_count} to {new_count} dependencies (+{delta}).",
                    evidence={"old_count": old_count, "new_count": new_count, "delta": delta},
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                ))

        # ── 5. Newly Orphaned Candidates ──────────────────────────────────────
        base_orphan_keys = {o.qualified_name for o in base_arch.orphans}
        for t_orphan in tgt_arch.orphans:
            if t_orphan.qualified_name not in base_orphan_keys:
                regressions.append(ArchitectureRegression(
                    regression_id=f"newly_orphaned:{t_orphan.qualified_name}",
                    regression_type=RegressionType.NEWLY_ORPHANED_CANDIDATE,
                    severity="low",
                    affected_entity=t_orphan.qualified_name,
                    message=f"Component '{t_orphan.qualified_name}' is newly orphaned with zero inbound architectural references.",
                    evidence={"exclusions_checked": t_orphan.exclusions_checked},
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                ))

        # ── 6. Resolution Regressions ─────────────────────────────────────────
        for rdiff in diff.resolution_changes:
            if rdiff.resolution_change:
                old_res, new_res = rdiff.resolution_change
                if old_res == "exact" and new_res in ("inferred", "unresolved"):
                    regressions.append(ArchitectureRegression(
                        regression_id=f"resolution_regression:{rdiff.canonical_id}",
                        regression_type=RegressionType.RESOLUTION_REGRESSION,
                        severity="medium",
                        affected_entity=rdiff.source_id,
                        message=f"Resolution confidence of relationship '{rdiff.canonical_id}' degraded from '{old_res}' to '{new_res}'.",
                        evidence={"old_resolution": old_res, "new_resolution": new_res, "target_id": rdiff.target_id},
                        repository_id=self.repository_id,
                        baseline_snapshot_id=self.baseline_snapshot_id,
                        target_snapshot_id=self.target_snapshot_id,
                    ))

        logger.info(
            "architecture_regressions_analyzed",
            total_regressions=len(regressions),
            new_cycles=sum(1 for r in regressions if r.regression_type == RegressionType.NEW_CYCLE),
            new_violations=sum(1 for r in regressions if r.regression_type == RegressionType.NEW_ARCHITECTURE_VIOLATION),
            hotspot_growth=sum(1 for r in regressions if r.regression_type == RegressionType.HOTSPOT_GROWTH),
            new_orphans=sum(1 for r in regressions if r.regression_type == RegressionType.NEWLY_ORPHANED_CANDIDATE),
            baseline_id=self.baseline_snapshot_id,
            target_id=self.target_snapshot_id,
        )
        return regressions
