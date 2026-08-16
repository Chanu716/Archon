import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict
from archon.models.evolution import EntityLifecycle, RelationshipChange, DriftFinding

class InvestigationContext(BaseModel):
    repository_id: uuid.UUID
    snapshot_id: uuid.UUID
    entity_id: str
    entity_name: str
    qualified_name: Optional[str] = None
    entity_type: str
    file_path: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class EntityOverview(BaseModel):
    complexity: Optional[float] = None
    coupling: Optional[float] = None
    risk: Optional[float] = None
    churn: Optional[int] = None
    callers: Optional[int] = None
    callees: Optional[int] = None

class CodeContext(BaseModel):
    source_code: str
    truncated: bool = False

class GraphContext(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

class HealthContext(BaseModel):
    metrics: Dict[str, float]
    sources: Dict[str, str]

class GitContext(BaseModel):
    commit_count: int = 0
    churn: int = 0
    first_changed_at: Optional[str] = None
    last_changed_at: Optional[str] = None
    recent_commits: List[Dict[str, Any]] = []

class ImpactContext(BaseModel):
    direct_callers: int = 0
    indirect_callers: int = 0
    direct_callees: int = 0
    indirect_callees: int = 0
    affected_entities: int = 0
    graph: Dict[str, Any]

class EvolutionContext(BaseModel):
    lifecycle: Optional[EntityLifecycle] = None
    relationship_changes: List[RelationshipChange] = []
    drift_findings: List[DriftFinding] = []

class SemanticContext(BaseModel):
    related_entities: List[Dict[str, Any]]

class InvestigationBaseResponse(BaseModel):
    context: InvestigationContext
    overview: EntityOverview
    code: Optional[CodeContext] = None
    graph: Optional[GraphContext] = None
    health: Optional[HealthContext] = None
