"""
Evolution Trend Analyzer (Slice ML-12)

Analyzes architectural metric trends over an explicitly ordered sequence of snapshots:
  - cycle_count
  - violation_count
  - hotspot_count
  - max_fan_in
  - max_fan_out
  - dependency_edge_count
  - orphan_candidate_count

Classifications:
  - increasing: monotonic non-decreasing with at least one increase
  - decreasing: monotonic non-increasing with at least one decrease
  - stable: all values identical
  - fluctuating: non-monotonic variance
  - insufficient_data: fewer than 2 snapshots
"""

from typing import List, Dict, Tuple, Optional
import structlog

from archon.pipeline.evolution.models import (
    TrendDirection,
    MetricTrend,
)
from archon.pipeline.architecture.models import ArchitectureAnalysisResult

logger = structlog.get_logger(__name__)


class EvolutionTrendAnalyzer:
    """
    Computes deterministic multi-snapshot architecture metric trends.
    """

    def analyze_trends(
        self,
        snapshot_history: List[Tuple[str, ArchitectureAnalysisResult]]
    ) -> List[MetricTrend]:
        """
        snapshot_history: Explicitly ordered list of (snapshot_id, analysis_result).
        """
        if len(snapshot_history) < 2:
            return [
                MetricTrend(
                    metric_name="all_metrics",
                    values=[(s_id, 0) for s_id, _ in snapshot_history],
                    direction=TrendDirection.INSUFFICIENT_DATA,
                    delta_total=0,
                    explanation="At least two snapshots are required to evaluate trends."
                )
            ]

        # Extract metric time series
        cycle_series: List[Tuple[str, int]] = []
        violation_series: List[Tuple[str, int]] = []
        hotspot_series: List[Tuple[str, int]] = []
        max_fan_in_series: List[Tuple[str, int]] = []
        max_fan_out_series: List[Tuple[str, int]] = []
        orphan_series: List[Tuple[str, int]] = []

        for s_id, arch in snapshot_history:
            cycle_series.append((s_id, len(arch.cycles)))
            violation_series.append((s_id, len(arch.violations)))
            hotspot_series.append((s_id, len(arch.hotspots)))
            orphan_series.append((s_id, len(arch.orphans)))

            max_fan_in = max((h.fan_in for h in arch.hotspots), default=0)
            max_fan_out = max((h.fan_out for h in arch.hotspots), default=0)
            max_fan_in_series.append((s_id, max_fan_in))
            max_fan_out_series.append((s_id, max_fan_out))

        metrics = [
            ("cycle_count", cycle_series),
            ("violation_count", violation_series),
            ("hotspot_count", hotspot_series),
            ("max_fan_in", max_fan_in_series),
            ("max_fan_out", max_fan_out_series),
            ("orphan_candidate_count", orphan_series),
        ]

        trends: List[MetricTrend] = []
        for name, series in metrics:
            direction, delta, explanation = self._classify_series(name, series)
            trends.append(MetricTrend(
                metric_name=name,
                values=series,
                direction=direction,
                delta_total=delta,
                explanation=explanation,
            ))

        return trends

    def _classify_series(
        self,
        metric_name: str,
        series: List[Tuple[str, int]]
    ) -> Tuple[TrendDirection, int, str]:
        values = [v for _, v in series]
        delta = values[-1] - values[0]

        is_all_equal = all(v == values[0] for v in values)
        if is_all_equal:
            return (
                TrendDirection.STABLE,
                0,
                f"Metric '{metric_name}' is stable at {values[0]} across {len(values)} snapshots."
            )

        is_non_decreasing = all(values[i] <= values[i + 1] for i in range(len(values) - 1))
        if is_non_decreasing and values[-1] > values[0]:
            return (
                TrendDirection.INCREASING,
                delta,
                f"Metric '{metric_name}' increased from {values[0]} to {values[-1]} (+{delta})."
            )

        is_non_increasing = all(values[i] >= values[i + 1] for i in range(len(values) - 1))
        if is_non_increasing and values[-1] < values[0]:
            return (
                TrendDirection.DECREASING,
                delta,
                f"Metric '{metric_name}' decreased from {values[0]} to {values[-1]} ({delta})."
            )

        return (
            TrendDirection.FLUCTUATING,
            delta,
            f"Metric '{metric_name}' fluctuated across snapshots (start: {values[0]}, end: {values[-1]})."
        )
