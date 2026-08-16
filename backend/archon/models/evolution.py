from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

class EntityLifecycleState(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    UNCHANGED = "UNCHANGED"

class MetricTrend(str, Enum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"

class DriftSeverity(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"

class MetricDelta(BaseModel):
    metric_name: str
    previous_value: Optional[float]
    current_value: Optional[float]
    delta: Optional[float]
    percentage_change: Optional[float]
    trend: Optional[MetricTrend] = None

class EntityLifecycle(BaseModel):
    entity_type: str # "File", "Module", "Function", "Class"
    qualified_name: str
    state: EntityLifecycleState
    metrics: Dict[str, MetricDelta] = Field(default_factory=dict)

class RelationshipChange(BaseModel):
    source_qname: str
    target_qname: str
    relationship_type: str # "CALLS", "IMPORTS", etc.
    state: EntityLifecycleState
    previous_resolution: Optional[str] = None
    current_resolution: Optional[str] = None

class DriftFinding(BaseModel):
    severity: DriftSeverity
    entity_name: str
    entity_type: str
    reason: str

class SnapshotMetadata(BaseModel):
    snapshot_id: uuid.UUID
    analyzed_at: datetime
    commit_sha: Optional[str]

class SnapshotComparison(BaseModel):
    repository_id: uuid.UUID
    previous_snapshot: SnapshotMetadata
    current_snapshot: SnapshotMetadata
    entities: List[EntityLifecycle] = Field(default_factory=list)
    relationships: List[RelationshipChange] = Field(default_factory=list)
    drift_findings: List[DriftFinding] = Field(default_factory=list)

class TimelineNode(BaseModel):
    snapshot_id: uuid.UUID
    analyzed_at: datetime
    commit_sha: Optional[str]
    total_files: int
    total_functions: int
    average_complexity: float
    average_coupling: float
    repository_risk: float
