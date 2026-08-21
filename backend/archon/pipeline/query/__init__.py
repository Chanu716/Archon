"""
Archon Architecture Query & Explainability Engine (Slice ML-13)
"""

from archon.pipeline.query.models import (
    QueryType,
    ResolutionConfidence,
    EntityResolutionStatus,
    ResolvedEntity,
    EntityResolutionResult,
    PathStep,
    TraversalPath,
    EvidenceFact,
    Explanation,
    ArchitectureQuery,
    HistoricalSnapshotFact,
    ArchitectureQueryResult,
)
from archon.pipeline.query.entity_resolver import EntityResolver
from archon.pipeline.query.traversal import ArchitectureTraversalEngine, DEFAULT_MAX_DEPTH, SUPPORTED_RELATIONSHIPS
from archon.pipeline.query.paths import DependencyPathFinder, MAX_QUERY_DEPTH, MAX_RETURNED_PATHS, HTTP_CHAIN_RELATIONSHIPS
from archon.pipeline.query.explain import ArchitectureExplanationBuilder
from archon.pipeline.query.history import ArchitectureHistoryService
from archon.pipeline.query.service import ArchitectureQueryService

__all__ = [
    "QueryType",
    "ResolutionConfidence",
    "EntityResolutionStatus",
    "ResolvedEntity",
    "EntityResolutionResult",
    "PathStep",
    "TraversalPath",
    "EvidenceFact",
    "Explanation",
    "ArchitectureQuery",
    "HistoricalSnapshotFact",
    "ArchitectureQueryResult",
    "EntityResolver",
    "ArchitectureTraversalEngine",
    "DEFAULT_MAX_DEPTH",
    "SUPPORTED_RELATIONSHIPS",
    "DependencyPathFinder",
    "MAX_QUERY_DEPTH",
    "MAX_RETURNED_PATHS",
    "HTTP_CHAIN_RELATIONSHIPS",
    "ArchitectureExplanationBuilder",
    "ArchitectureHistoryService",
    "ArchitectureQueryService",
]
