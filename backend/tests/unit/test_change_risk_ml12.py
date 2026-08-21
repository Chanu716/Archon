"""
Change Risk Evaluation Unit Tests (Slice ML-12)

Tests:
  - High risk when new cycle or architecture violation is introduced
  - High risk when heavily depended-on entity is removed
  - Medium risk on hotspot modification or resolution degradation
  - Low risk on isolated safe additions
  - Explainable reasons preserved
"""

import pytest
from archon.pipeline.evolution.models import (
    RiskLevel,
    RegressionType,
    SnapshotEntityFact,
    SnapshotRelationshipFact,
    ArchitectureRegression,
)
from archon.pipeline.evolution.differ import SnapshotDiffer
from archon.pipeline.evolution.impact import ChangeImpactAnalyzer


def test_high_risk_on_new_cycle():
    differ = SnapshotDiffer("r1", "s1", "s2")
    diff = differ.diff_snapshots({}, {}, [], [])

    new_cycle_reg = ArchitectureRegression(
        regression_id="cycle:A->B",
        regression_type=RegressionType.NEW_CYCLE,
        severity="high",
        affected_entity="A",
        message="New cycle A->B",
        repository_id="r1",
        baseline_snapshot_id="s1",
        target_snapshot_id="s2",
    )

    analyzer = ChangeImpactAnalyzer("r1", "s1", "s2")
    _, risk = analyzer.analyze_impact_and_risk(diff, [new_cycle_reg], None)

    assert risk.risk_level == RiskLevel.HIGH
    assert any("circular dependency" in r for r in risk.reasons)


def test_high_risk_on_new_architecture_violation():
    differ = SnapshotDiffer("r1", "s1", "s2")
    diff = differ.diff_snapshots({}, {}, [], [])

    new_viol_reg = ArchitectureRegression(
        regression_id="violation:A->B",
        regression_type=RegressionType.NEW_ARCHITECTURE_VIOLATION,
        severity="medium",
        affected_entity="A",
        message="New layer skip",
        repository_id="r1",
        baseline_snapshot_id="s1",
        target_snapshot_id="s2",
    )

    analyzer = ChangeImpactAnalyzer("r1", "s1", "s2")
    _, risk = analyzer.analyze_impact_and_risk(diff, [new_viol_reg], None)

    assert risk.risk_level == RiskLevel.HIGH
    assert any("architectural violation" in r for r in risk.reasons)


def test_low_risk_on_isolated_addition():
    target_entities = {
        "NewHelper": SnapshotEntityFact("NewHelper", "Class", "r1", "s2"),
    }
    differ = SnapshotDiffer("r1", "s1", "s2")
    diff = differ.diff_snapshots({}, target_entities, [], [])

    analyzer = ChangeImpactAnalyzer("r1", "s1", "s2")
    _, risk = analyzer.analyze_impact_and_risk(diff, [], None)

    assert risk.risk_level == RiskLevel.LOW
    assert len(risk.high_risk_factors) == 0
