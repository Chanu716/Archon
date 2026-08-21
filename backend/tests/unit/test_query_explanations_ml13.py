"""
Architecture Explanation Builder Unit Tests (Slice ML-13)

Tests:
  - Risk explanation (High/Med/Low with evidence)
  - Violation explanation (layer skips, boundary rules)
  - Cycle explanation (canonical loop path)
  - Hotspot explanation (fan-in, percentiles)
  - Orphan explanation (candidate orphan safeguards)
"""

import pytest
from archon.pipeline.evolution.models import (
    ChangeRiskFact,
    RiskLevel,
    ArchitectureRegression,
    RegressionType,
)
from archon.pipeline.architecture.models import (
    ArchitectureViolation,
    ArchitectureCycle,
    HotspotFact,
    OrphanFact,
)
from archon.pipeline.query.explain import ArchitectureExplanationBuilder


def test_risk_explanation_generation():
    builder = ArchitectureExplanationBuilder("r1", "s1")
    risk_fact = ChangeRiskFact(
        risk_level=RiskLevel.HIGH,
        score=85,
        reasons=["Introduced 1 new circular dependency cycle(s)", "Introduced 1 new architectural violation(s)"],
        high_risk_factors=["Introduced 1 new circular dependency cycle(s)"],
        medium_risk_factors=[],
        repository_id="r1",
        baseline_snapshot_id="s1",
        target_snapshot_id="s2",
    )
    regressions = [
        ArchitectureRegression("cycle:A->B", RegressionType.NEW_CYCLE, "high", "OrderService", "New cycle OrderService <-> PaymentService", {}, "r1", "s1", "s2"),
    ]

    explanation, evidence = builder.explain_risk("OrderService", risk_fact, regressions)

    assert "HIGH" in explanation.summary
    assert any("HIGH RISK" in r for r in explanation.detailed_reasons)
    assert any("Triggering regression" in r for r in explanation.detailed_reasons)
    assert len(evidence) >= 2


def test_violation_explanation_generation():
    builder = ArchitectureExplanationBuilder("r1", "s1")
    viol = ArchitectureViolation(
        source_qualified_name="OrderController",
        target_qualified_name="SqlOrderRepository",
        violation_type="layer_skip",
        severity="medium",
        resolution="exact",
        evidence_type="resolved_dependency_path",
        message="Presentation layer directly accesses Infrastructure without Application layer",
        repository_id="r1",
        snapshot_id="s1",
        source_layer="presentation",
        target_layer="infrastructure",
    )

    explanation, evidence = builder.explain_violation(viol)

    assert "layer_skip" in explanation.summary
    assert any("Presentation" in r for r in explanation.detailed_reasons)
    assert any("Infrastructure" in r for r in explanation.detailed_reasons)
    assert len(evidence) == 1


def test_cycle_explanation_generation():
    builder = ArchitectureExplanationBuilder("r1", "s1")
    cycle = ArchitectureCycle("cycle:A->B", ["ServiceA", "ServiceB"], ["CALLS", "CALLS"], "medium", "r1", "s1", "description")

    explanation, evidence = builder.explain_cycle(cycle)

    assert "Circular dependency" in explanation.summary
    assert any("ServiceA -> ServiceB -> ServiceA" in r for r in explanation.detailed_reasons)
    assert len(evidence) == 1
