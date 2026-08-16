"""
Domain models for Impact Analysis.

These are runtime dataclasses, not database models. Impact is computed
on-demand from the Neo4j graph — it is never persisted to PostgreSQL.

Why not persist? Impact is a function of the graph at query-time. Persisting
it would create stale data. The live graph is always the authoritative source.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ImpactedEntity:
    """A single entity identified as impacted by a change."""
    id: str                         # Neo4j element ID
    type: str                       # Function, Class, Module, File, etc.
    name: str                       # Display name
    qualified_name: Optional[str]   # Fully-qualified name where available
    file: Optional[str]             # Path to containing file
    distance: int                   # Hop distance from target (1 = direct, >1 = indirect)
    relationship: str               # Relationship type that establishes the impact (e.g. CALLS)
    resolution: str                 # 'exact' | 'inferred' | 'unresolved'
    path: List[str] = field(default_factory=list)  # Name path from entity to target


@dataclass
class TraversalMetadata:
    """Describes how the traversal was constrained."""
    max_depth: int
    max_nodes: int
    actual_depth_reached: int
    nodes_visited: int
    truncated: bool


@dataclass
class ImpactSummary:
    """Counts of impacted entities per category."""
    direct_callers: int = 0
    indirect_callers: int = 0
    direct_callees: int = 0
    indirect_callees: int = 0
    affected_files: int = 0
    affected_modules: int = 0
    affected_classes: int = 0
    unresolved_references: int = 0


@dataclass
class ImpactResult:
    """
    The complete impact analysis result for a target entity.

    Direction definitions:
      - upstream (callers): entities that depend on the target
      - downstream (callees): entities the target depends on

    Resolution definitions:
      - exact: confirmed by static analysis
      - inferred: reasonable inference (e.g. self.method()), result labeled accordingly
      - unresolved: cannot be confirmed, surfaced separately
    """
    target_id: str
    target_name: str
    target_type: str
    snapshot_id: str

    direct_callers: List[ImpactedEntity] = field(default_factory=list)
    indirect_callers: List[ImpactedEntity] = field(default_factory=list)
    direct_callees: List[ImpactedEntity] = field(default_factory=list)
    indirect_callees: List[ImpactedEntity] = field(default_factory=list)

    affected_files: List[str] = field(default_factory=list)
    affected_modules: List[str] = field(default_factory=list)
    affected_classes: List[str] = field(default_factory=list)

    unresolved_references: List[ImpactedEntity] = field(default_factory=list)

    summary: ImpactSummary = field(default_factory=ImpactSummary)
    traversal: TraversalMetadata = field(default_factory=lambda: TraversalMetadata(
        max_depth=5, max_nodes=500, actual_depth_reached=0, nodes_visited=0, truncated=False
    ))
