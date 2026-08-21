"""
Architecture Query & Explainability Domain Models (Slice ML-13)

Defines structured models for:
  - Architecture queries & query results
  - Entity resolution candidates and resolution statuses
  - Traversal requests, paths, and path steps
  - First-class auditable Evidence facts
  - Deterministic, evidence-backed explanations
  - Temporal historical query results
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Set, Any, Tuple


class QueryType(str, Enum):
    UPSTREAM_DEPENDENTS = "upstream_dependents"
    DOWNSTREAM_DEPENDENCIES = "downstream_dependencies"
    DEPENDENCY_PATH = "dependency_path"
    HTTP_ARCHITECTURE_PATH = "http_architecture_path"
    EXPLAIN_RISK = "explain_risk"
    EXPLAIN_VIOLATION = "explain_violation"
    EXPLAIN_CYCLE = "explain_cycle"
    EXPLAIN_HOTSPOT = "explain_hotspot"
    EXPLAIN_ORPHAN = "explain_orphan"
    ENTITY_HISTORY = "entity_history"
    ISSUE_ORIGIN = "issue_origin"
    RISK_EVOLUTION = "risk_evolution"
    TREND = "trend"


class ResolutionConfidence(str, Enum):
    EXACT = "exact"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


class EntityResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass
class ResolvedEntity:
    """Canonical architectural entity resolved from a query reference."""
    canonical_id: str
    qualified_name: str
    entity_kind: str  # "Class" | "Function" | "Module" | "Endpoint"
    repository_id: str
    snapshot_id: str
    module_name: Optional[str] = None
    file_path: Optional[str] = None
    architecture_role: Optional[str] = None
    architecture_layer: Optional[str] = None
    confidence: ResolutionConfidence = ResolutionConfidence.EXACT


@dataclass
class EntityResolutionResult:
    """Result of attempting to resolve a raw entity query string."""
    query_string: str
    status: EntityResolutionStatus
    entity: Optional[ResolvedEntity] = None
    candidates: List[ResolvedEntity] = field(default_factory=list)
    message: str = ""


@dataclass
class PathStep:
    """A single hop in an architectural graph path."""
    source_id: str
    relationship: str
    target_id: str
    source_role: Optional[str] = None
    target_role: Optional[str] = None
    source_layer: Optional[str] = None
    target_layer: Optional[str] = None
    resolution: str = "exact"
    evidence_type: str = ""


@dataclass
class TraversalPath:
    """An end-to-end architectural chain or path between entities."""
    start_entity: str
    end_entity: str
    steps: List[PathStep] = field(default_factory=list)
    length: int = 0
    confidence: ResolutionConfidence = ResolutionConfidence.EXACT


@dataclass
class EvidenceFact:
    """An auditable atomic fact collected to prove an explanation or query result."""
    fact_type: str  # "relationship" | "role" | "layer" | "cycle" | "hotspot" | "orphan" | "violation" | "regression" | "change_risk" | "trend" | "entity_diff"
    source_id: str
    target_id: Optional[str] = None
    relationship_type: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    confidence: ResolutionConfidence = ResolutionConfidence.EXACT
    repository_id: str = ""
    snapshot_id: str = ""


@dataclass
class Explanation:
    """Evidence-backed human-readable explanation derived exclusively from EvidenceFacts."""
    summary: str
    detailed_reasons: List[str] = field(default_factory=list)
    rule_references: List[str] = field(default_factory=list)
    evidence_fact_ids: List[str] = field(default_factory=list)


@dataclass
class ArchitectureQuery:
    """Structured query specification."""
    repository_id: str
    snapshot_id: str
    query_type: QueryType
    entity: Optional[str] = None
    target_entity: Optional[str] = None
    baseline_snapshot_id: Optional[str] = None
    max_depth: int = 5
    relationship_types: Optional[List[str]] = None
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HistoricalSnapshotFact:
    """Historical timeline observation for an entity or issue."""
    snapshot_id: str
    fact_value: Any
    description: str
    evidence: List[EvidenceFact] = field(default_factory=list)


@dataclass
class ArchitectureQueryResult:
    """Top-level structured query result."""
    query_type: QueryType
    repository_id: str
    snapshot_id: str
    resolved_entity: Optional[ResolvedEntity] = None
    target_resolved_entity: Optional[ResolvedEntity] = None
    paths: List[TraversalPath] = field(default_factory=list)
    evidence: List[EvidenceFact] = field(default_factory=list)
    explanation: Optional[Explanation] = None
    history: List[HistoricalSnapshotFact] = field(default_factory=list)
    confidence: ResolutionConfidence = ResolutionConfidence.EXACT
    warnings: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
