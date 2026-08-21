"""
Architecture Intelligence Domain Models (Slice ML-11)

Defines canonical data structures for:
  - Architecture node classifications (Role & Layer)
  - Boundary facts and layer transitions
  - Circular dependencies
  - Dependency hotspots
  - Candidate orphaned components
  - Architectural violations (Layer skip, Reverse dependency, Boundary bypass)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Set, Any


class ArchitectureRole(str, Enum):
    CONTROLLER = "controller"
    ENDPOINT_HANDLER = "endpoint_handler"
    SERVICE = "service"
    REPOSITORY = "repository"
    GATEWAY = "gateway"
    CLIENT = "client"
    COMPONENT = "component"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    UTILITY = "utility"
    UNKNOWN = "unknown"


class ArchitectureLayer(str, Enum):
    PRESENTATION = "presentation"
    APPLICATION = "application"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


ROLE_TO_LAYER: Dict[ArchitectureRole, ArchitectureLayer] = {
    ArchitectureRole.CONTROLLER: ArchitectureLayer.PRESENTATION,
    ArchitectureRole.ENDPOINT_HANDLER: ArchitectureLayer.PRESENTATION,
    ArchitectureRole.COMPONENT: ArchitectureLayer.PRESENTATION,
    ArchitectureRole.SERVICE: ArchitectureLayer.APPLICATION,
    ArchitectureRole.DOMAIN: ArchitectureLayer.DOMAIN,
    ArchitectureRole.REPOSITORY: ArchitectureLayer.INFRASTRUCTURE,
    ArchitectureRole.GATEWAY: ArchitectureLayer.INFRASTRUCTURE,
    ArchitectureRole.CLIENT: ArchitectureLayer.INFRASTRUCTURE,
    ArchitectureRole.INFRASTRUCTURE: ArchitectureLayer.INFRASTRUCTURE,
    ArchitectureRole.UTILITY: ArchitectureLayer.UNKNOWN,
    ArchitectureRole.UNKNOWN: ArchitectureLayer.UNKNOWN,
}


@dataclass
class ArchitectureNodeFact:
    """Represents the architectural classification of a Class, Struct, or Function node."""
    qualified_name: str
    node_kind: str  # "Class" | "Function" | "Module"
    architecture_role: ArchitectureRole
    layer: ArchitectureLayer
    resolution: str  # "exact" | "inferred" | "unresolved"
    evidence_type: str
    evidence: str
    repository_id: str
    snapshot_id: str
    file_path: Optional[str] = None
    language: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchitectureCycle:
    """Represents a canonical directed dependency cycle."""
    cycle_id: str
    members: List[str]
    relationship_types: List[str]
    severity: str  # "medium" | "high"
    repository_id: str
    snapshot_id: str
    description: str


@dataclass
class HotspotFact:
    """Represents an architectural hotspot based on graph fan-in / fan-out topology."""
    qualified_name: str
    node_kind: str
    fan_in: int
    fan_out: int
    transitive_dependents: int
    percentile: float
    severity: str  # "low" | "medium" | "high"
    explanation: str
    repository_id: str
    snapshot_id: str


@dataclass
class OrphanFact:
    """Represents a candidate orphaned component with zero meaningful inbound references."""
    qualified_name: str
    node_kind: str
    resolution: str = "inferred"
    evidence_type: str = "zero_meaningful_inbound_edges"
    exclusions_checked: List[str] = field(default_factory=list)
    repository_id: str = ""
    snapshot_id: str = ""
    file_path: Optional[str] = None


@dataclass
class ArchitectureViolation:
    """Represents a deterministic rule-based architectural violation."""
    source_qualified_name: str
    target_qualified_name: str
    violation_type: str  # "layer_skip" | "reverse_dependency" | "circular_dependency" | "boundary_bypass"
    severity: str        # "low" | "medium" | "high"
    resolution: str      # "exact" | "inferred"
    evidence_type: str
    message: str
    repository_id: str
    snapshot_id: str
    source_layer: Optional[str] = None
    target_layer: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchitectureAnalysisResult:
    """Aggregated result of the architecture intelligence pipeline."""
    nodes: Dict[str, ArchitectureNodeFact] = field(default_factory=dict)
    cycles: List[ArchitectureCycle] = field(default_factory=list)
    hotspots: List[HotspotFact] = field(default_factory=list)
    orphans: List[OrphanFact] = field(default_factory=list)
    violations: List[ArchitectureViolation] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
