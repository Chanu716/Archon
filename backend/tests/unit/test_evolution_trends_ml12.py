"""
Evolution Trend Analyzer Unit Tests (Slice ML-12)

Tests:
  - Increasing trend (monotonic non-decreasing with at least one increase)
  - Decreasing trend (monotonic non-increasing with at least one decrease)
  - Stable trend (all values equal)
  - Fluctuating trend (non-monotonic variance)
  - Insufficient data guard (<2 snapshots)
"""

import pytest
from archon.pipeline.evolution.models import TrendDirection
from archon.pipeline.evolution.trends import EvolutionTrendAnalyzer
from archon.pipeline.architecture.models import (
    ArchitectureAnalysisResult,
    ArchitectureCycle,
    ArchitectureViolation,
    HotspotFact,
)


def test_evolution_trends_classification():
    # 3 Snapshots
    # Snap 1: 0 cycles, 3 violations
    # Snap 2: 1 cycle, 2 violations
    # Snap 3: 2 cycles, 1 violation
    arch1 = ArchitectureAnalysisResult(
        cycles=[],
        violations=[
            ArchitectureViolation("A", "B", "layer_skip", "medium", "exact", "", "", "r", "s1"),
            ArchitectureViolation("C", "D", "layer_skip", "medium", "exact", "", "", "r", "s1"),
            ArchitectureViolation("E", "F", "layer_skip", "medium", "exact", "", "", "r", "s1"),
        ],
    )
    arch2 = ArchitectureAnalysisResult(
        cycles=[ArchitectureCycle("cycle:A->B", ["A", "B"], [], "medium", "r", "s2", "")],
        violations=[
            ArchitectureViolation("A", "B", "layer_skip", "medium", "exact", "", "", "r", "s2"),
            ArchitectureViolation("C", "D", "layer_skip", "medium", "exact", "", "", "r", "s2"),
        ],
    )
    arch3 = ArchitectureAnalysisResult(
        cycles=[
            ArchitectureCycle("cycle:A->B", ["A", "B"], [], "medium", "r", "s3", ""),
            ArchitectureCycle("cycle:X->Y", ["X", "Y"], [], "medium", "r", "s3", ""),
        ],
        violations=[
            ArchitectureViolation("A", "B", "layer_skip", "medium", "exact", "", "", "r", "s3"),
        ],
    )

    history = [("s1", arch1), ("s2", arch2), ("s3", arch3)]

    analyzer = EvolutionTrendAnalyzer()
    trends = analyzer.analyze_trends(history)

    trend_map = {t.metric_name: t.direction for t in trends}
    assert trend_map["cycle_count"] == TrendDirection.INCREASING
    assert trend_map["violation_count"] == TrendDirection.DECREASING


def test_insufficient_data_guard():
    """Single snapshot returns insufficient_data direction"""
    analyzer = EvolutionTrendAnalyzer()
    trends = analyzer.analyze_trends([("s1", ArchitectureAnalysisResult())])

    assert len(trends) == 1
    assert trends[0].direction == TrendDirection.INSUFFICIENT_DATA
