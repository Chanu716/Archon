"""
Archon Architecture Evolution & Change Intelligence Engine (Slice ML-12)
"""

from archon.pipeline.evolution.models import (
    ChangeType,
    RegressionType,
    TrendDirection,
    RiskLevel,
    SnapshotEntityFact,
    SnapshotRelationshipFact,
    EntityDiff,
    RelationshipDiff,
    SnapshotDiffResult,
    ArchitectureChangeFact,
    ArchitectureRegression,
    ChangeImpactFact,
    ChangeRiskFact,
    MetricTrend,
    EvolutionAnalysisResult,
)
from archon.pipeline.evolution.differ import SnapshotDiffer
from archon.pipeline.evolution.changes import ArchitectureChangeAnalyzer
from archon.pipeline.evolution.regressions import (
    ArchitectureRegressionAnalyzer,
    HOTSPOT_GROWTH_FAN_IN_DELTA,
    HOTSPOT_GROWTH_FAN_OUT_DELTA,
    DEPENDENCY_GROWTH_DELTA,
)
from archon.pipeline.evolution.impact import ChangeImpactAnalyzer, MAX_IMPACT_DEPTH
from archon.pipeline.evolution.trends import EvolutionTrendAnalyzer
from archon.pipeline.evolution.service import ArchitectureEvolutionService

__all__ = [
    "ChangeType",
    "RegressionType",
    "TrendDirection",
    "RiskLevel",
    "SnapshotEntityFact",
    "SnapshotRelationshipFact",
    "EntityDiff",
    "RelationshipDiff",
    "SnapshotDiffResult",
    "ArchitectureChangeFact",
    "ArchitectureRegression",
    "ChangeImpactFact",
    "ChangeRiskFact",
    "MetricTrend",
    "EvolutionAnalysisResult",
    "SnapshotDiffer",
    "ArchitectureChangeAnalyzer",
    "ArchitectureRegressionAnalyzer",
    "HOTSPOT_GROWTH_FAN_IN_DELTA",
    "HOTSPOT_GROWTH_FAN_OUT_DELTA",
    "DEPENDENCY_GROWTH_DELTA",
    "ChangeImpactAnalyzer",
    "MAX_IMPACT_DEPTH",
    "EvolutionTrendAnalyzer",
    "ArchitectureEvolutionService",
]
