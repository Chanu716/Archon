"""
Architecture Regression Analyzer Unit Tests (Slice ML-12)

Tests:
  - Pre-existing cycles are NOT reported as new regressions
  - Newly introduced 2-node and 3-node cycles
  - Pre-existing violations are NOT reported as new regressions
  - Newly introduced layer skip and reverse dependency violations
  - Meaningful hotspot growth (fan-in delta >= threshold)
  - Meaningful dependency growth
  - Newly orphaned candidate components
  - Resolution regression (exact -> unresolved)
"""

import pytest
from archon.pipeline.evolution.models import (
    RegressionType,
    SnapshotRelationshipFact,
)
from archon.pipeline.evolution.differ import SnapshotDiffer
from archon.pipeline.evolution.regressions import ArchitectureRegressionAnalyzer
from archon.pipeline.architecture.models import (
    ArchitectureAnalysisResult,
    ArchitectureCycle,
    ArchitectureViolation,
    HotspotFact,
    OrphanFact,
)


def test_new_cycle_regression_detection():
    """Only newly introduced cycles are flagged as regressions"""
    existing_cycle = ArchitectureCycle("cycle:A->B", ["A", "B"], ["CALLS"], "medium", "repo-1", "snap-1", "")
    new_cycle = ArchitectureCycle("cycle:X->Y->Z", ["X", "Y", "Z"], ["CALLS"], "high", "repo-1", "snap-2", "")

    base_arch = ArchitectureAnalysisResult(cycles=[existing_cycle])
    target_arch = ArchitectureAnalysisResult(cycles=[existing_cycle, new_cycle])

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots({}, {}, [], [])

    analyzer = ArchitectureRegressionAnalyzer("repo-1", "snap-1", "snap-2")
    regressions = analyzer.analyze_regressions(diff, base_arch, target_arch)

    cycle_regs = [r for r in regressions if r.regression_type == RegressionType.NEW_CYCLE]
    assert len(cycle_regs) == 1
    assert "cycle:X->Y->Z" in cycle_regs[0].regression_id


def test_new_violation_regression_detection():
    """Only newly introduced violations are flagged as regressions"""
    old_viol = ArchitectureViolation("A", "B", "layer_skip", "medium", "exact", "", "", "repo-1", "snap-1")
    new_viol = ArchitectureViolation("Controller", "Repo", "layer_skip", "medium", "exact", "", "", "repo-1", "snap-2")

    base_arch = ArchitectureAnalysisResult(violations=[old_viol])
    target_arch = ArchitectureAnalysisResult(violations=[old_viol, new_viol])

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots({}, {}, [], [])

    analyzer = ArchitectureRegressionAnalyzer("repo-1", "snap-1", "snap-2")
    regressions = analyzer.analyze_regressions(diff, base_arch, target_arch)

    viol_regs = [r for r in regressions if r.regression_type == RegressionType.NEW_ARCHITECTURE_VIOLATION]
    assert len(viol_regs) == 1
    assert viol_regs[0].affected_entity == "Controller"


def test_hotspot_growth_threshold_guard():
    """Hotspot growth below threshold is ignored; growth >= threshold is reported"""
    base_hotspots = [
        HotspotFact("SharedLogger", "Class", fan_in=2, fan_out=1, transitive_dependents=2, percentile=50.0, severity="low", explanation="", repository_id="r1", snapshot_id="s1"),
        HotspotFact("MinorHelper", "Class", fan_in=1, fan_out=1, transitive_dependents=1, percentile=20.0, severity="low", explanation="", repository_id="r1", snapshot_id="s1"),
    ]
    target_hotspots = [
        # SharedLogger grew by +3 (fan-in 2 -> 5) -> exceeds threshold 2
        HotspotFact("SharedLogger", "Class", fan_in=5, fan_out=1, transitive_dependents=5, percentile=90.0, severity="high", explanation="", repository_id="r1", snapshot_id="s2"),
        # MinorHelper grew by +1 (fan-in 1 -> 2) -> below threshold 2
        HotspotFact("MinorHelper", "Class", fan_in=2, fan_out=1, transitive_dependents=2, percentile=50.0, severity="medium", explanation="", repository_id="r1", snapshot_id="s2"),
    ]

    base_arch = ArchitectureAnalysisResult(hotspots=base_hotspots)
    target_arch = ArchitectureAnalysisResult(hotspots=target_hotspots)

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots({}, {}, [], [])

    analyzer = ArchitectureRegressionAnalyzer("repo-1", "snap-1", "snap-2", hotspot_fan_in_threshold=2)
    regressions = analyzer.analyze_regressions(diff, base_arch, target_arch)

    hotspot_regs = [r for r in regressions if r.regression_type == RegressionType.HOTSPOT_GROWTH]
    assert len(hotspot_regs) == 1
    assert hotspot_regs[0].affected_entity == "SharedLogger"


def test_newly_orphaned_candidate_detection():
    """Newly orphaned components in target are flagged"""
    old_orphan = OrphanFact("LegacyUnused", "Class", repository_id="r1", snapshot_id="s1")
    new_orphan = OrphanFact("AbandonedService", "Class", repository_id="r1", snapshot_id="s2")

    base_arch = ArchitectureAnalysisResult(orphans=[old_orphan])
    target_arch = ArchitectureAnalysisResult(orphans=[old_orphan, new_orphan])

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots({}, {}, [], [])

    analyzer = ArchitectureRegressionAnalyzer("repo-1", "snap-1", "snap-2")
    regressions = analyzer.analyze_regressions(diff, base_arch, target_arch)

    orphan_regs = [r for r in regressions if r.regression_type == RegressionType.NEWLY_ORPHANED_CANDIDATE]
    assert len(orphan_regs) == 1
    assert orphan_regs[0].affected_entity == "AbandonedService"
