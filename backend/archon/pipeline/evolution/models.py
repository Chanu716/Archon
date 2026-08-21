"""
Architecture Evolution & Change Intelligence Domain Models (Slice ML-12)

Defines canonical data structures for:
  - Snapshot entity facts and graph relationship facts
  - Entity & relationship diffs (added, removed, modified, unchanged)
  - Architectural changes (roles, layers, endpoints, dependencies, resolution confidence)
  - Architectural regressions (new cycles, new violations, hotspot growth, newly orphaned candidates)
  - Multi-snapshot evolution trends (increasing, decreasing, stable, fluctuating)
  - Change blast radius impact and explainable change risk classification
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Set, Any, Tuple


class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class RegressionType(str, Enum):
    NEW_CYCLE = "new_cycle"
    NEW_ARCHITECTURE_VIOLATION = "new_architecture_violation"
    HOTSPOT_GROWTH = "hotspot_growth"
    DEPENDENCY_GROWTH = "dependency_growth"
    NEWLY_ORPHANED_CANDIDATE = "newly_orphaned_candidate"
    RESOLUTION_REGRESSION = "resolution_regression"
    BOUNDARY_REGRESSION = "boundary_regression"
    REVERSE_DEPENDENCY_REGRESSION = "reverse_dependency_regression"


class TrendDirection(str, Enum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    FLUCTUATING = "fluctuating"
    INSUFFICIENT_DATA = "insufficient_data"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class SnapshotEntityFact:
    """Represents a canonical entity in one snapshot."""
    qualified_name: str
    entity_kind: str  # "Class" | "Function" | "Module" | "Endpoint"
    repository_id: str
    snapshot_id: str
    module_name: Optional[str] = None
    file_path: Optional[str] = None
    architecture_role: Optional[str] = None
    architecture_layer: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SnapshotRelationshipFact:
    """Represents a canonical graph relationship in one snapshot."""
    source_id: str
    relationship_type: str
    target_id: str
    repository_id: str
    snapshot_id: str
    resolution: str = "exact"  # "exact" | "inferred" | "unresolved"
    evidence_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def canonical_id(self) -> str:
        return f"{self.source_id}->{self.relationship_type}->{self.target_id}"


@dataclass
class EntityDiff:
    """Diff result for a single entity across two snapshots."""
    qualified_name: str
    entity_kind: str
    change_type: ChangeType
    baseline_entity: Optional[SnapshotEntityFact] = None
    target_entity: Optional[SnapshotEntityFact] = None
    field_changes: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)  # field_name -> (old_val, new_val)


@dataclass
class RelationshipDiff:
    """Diff result for a single relationship across two snapshots."""
    canonical_id: str
    source_id: str
    relationship_type: str
    target_id: str
    change_type: ChangeType
    baseline_rel: Optional[SnapshotRelationshipFact] = None
    target_rel: Optional[SnapshotRelationshipFact] = None
    resolution_change: Optional[Tuple[str, str]] = None  # (old_resolution, new_resolution)


@dataclass
class SnapshotDiffResult:
    """Aggregated raw diff between baseline and target snapshots."""
    repository_id: str
    baseline_snapshot_id: str
    target_snapshot_id: str
    entity_diffs: Dict[str, EntityDiff] = field(default_factory=dict)
    relationship_diffs: Dict[str, RelationshipDiff] = field(default_factory=dict)
    added_entities: List[str] = field(default_factory=list)
    removed_entities: List[str] = field(default_factory=list)
    modified_entities: List[str] = field(default_factory=list)
    added_relationships: List[str] = field(default_factory=list)
    removed_relationships: List[str] = field(default_factory=list)
    resolution_changes: List[RelationshipDiff] = field(default_factory=list)


@dataclass
class ArchitectureChangeFact:
    """Semantic architectural change between baseline and target snapshots."""
    change_id: str
    category: str  # "role_change" | "layer_change" | "dependency_added" | "dependency_removed" | "endpoint_added" | "endpoint_removed" | "resolution_improved" | "resolution_degraded"
    entity_id: str
    description: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    repository_id: str = ""
    baseline_snapshot_id: str = ""
    target_snapshot_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchitectureRegression:
    """Represents a negative architectural regression introduced in target snapshot."""
    regression_id: str
    regression_type: RegressionType
    severity: str  # "low" | "medium" | "high"
    affected_entity: str
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    repository_id: str = ""
    baseline_snapshot_id: str = ""
    target_snapshot_id: str = ""


@dataclass
class ChangeImpactFact:
    """Represents direct and transitive architectural blast radius of changes."""
    changed_entity: str
    direct_dependents: List[str] = field(default_factory=list)
    direct_dependencies: List[str] = field(default_factory=list)
    transitive_impacted_nodes: List[str] = field(default_factory=list)
    impact_depth: int = 0
    blast_radius_score: int = 0


@dataclass
class ChangeRiskFact:
    """Explainable risk evaluation for snapshot transition."""
    risk_level: RiskLevel
    score: int
    reasons: List[str]
    high_risk_factors: List[str] = field(default_factory=list)
    medium_risk_factors: List[str] = field(default_factory=list)
    repository_id: str = ""
    baseline_snapshot_id: str = ""
    target_snapshot_id: str = ""


@dataclass
class MetricTrend:
    """Trend analysis for a specific metric over ordered sequence of snapshots."""
    metric_name: str
    values: List[Tuple[str, int]]  # (snapshot_id, value)
    direction: TrendDirection
    delta_total: int
    explanation: str


@dataclass
class EvolutionAnalysisResult:
    """Top-level aggregated result of Architecture Evolution Engine."""
    repository_id: str
    baseline_snapshot_id: str
    target_snapshot_id: str
    diff: SnapshotDiffResult
    architecture_changes: List[ArchitectureChangeFact] = field(default_factory=list)
    regressions: List[ArchitectureRegression] = field(default_factory=list)
    impact_facts: List[ChangeImpactFact] = field(default_factory=list)
    risk: Optional[ChangeRiskFact] = None
    trends: List[MetricTrend] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
