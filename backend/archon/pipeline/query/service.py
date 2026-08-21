"""
Architecture Query & Explainability Service (Slice ML-13)

Central entry point and dispatcher for architecture queries:
  - Entity Resolution (Exact, Unambiguous Short Name, Endpoints, Modules)
  - Upstream Dependents & Downstream Dependencies
  - General Dependency Paths & Full HTTP Request Architecture Chains
  - Explainability Engine (Risk, Violations, Cycles, Hotspots, Candidate Orphans)
  - Historical & Temporal Queries (Entity History, Issue Origins, Risk Evolution, Trends)

Guarantees:
  - Structured facts first; explanations synthesized strictly from EvidenceFacts.
  - Zero hallucination or unverified causal assertions.
  - Strict repository and snapshot scoping.
"""

from typing import List, Dict, Optional, Set, Tuple, Any
import structlog

from archon.pipeline.architecture.models import (
    ArchitectureAnalysisResult,
    ArchitectureViolation,
    ArchitectureCycle,
    HotspotFact,
    OrphanFact,
)
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
    EvolutionAnalysisResult,
    ChangeRiskFact,
    ArchitectureRegression,
)
from archon.pipeline.query.models import (
    QueryType,
    ResolutionConfidence,
    EntityResolutionStatus,
    ResolvedEntity,
    EntityResolutionResult,
    ArchitectureQuery,
    ArchitectureQueryResult,
    TraversalPath,
    EvidenceFact,
    Explanation,
)
from archon.pipeline.query.entity_resolver import EntityResolver
from archon.pipeline.query.traversal import ArchitectureTraversalEngine
from archon.pipeline.query.paths import DependencyPathFinder
from archon.pipeline.query.explain import ArchitectureExplanationBuilder
from archon.pipeline.query.history import ArchitectureHistoryService

logger = structlog.get_logger(__name__)


class ArchitectureQueryService:
    """
    Unified, deterministic query engine for architecture graph facts and evolution timelines.
    """

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

        self.entity_resolver = EntityResolver(self.repository_id, self.snapshot_id)
        self.traversal_engine = ArchitectureTraversalEngine(self.repository_id, self.snapshot_id)
        self.path_finder = DependencyPathFinder(self.repository_id, self.snapshot_id)
        self.explanation_builder = ArchitectureExplanationBuilder(self.repository_id, self.snapshot_id)
        self.history_service = ArchitectureHistoryService(self.repository_id)

    def resolve_entity(
        self,
        query_string: str,
        entities: Dict[str, SnapshotEntityFact],
    ) -> EntityResolutionResult:
        return self.entity_resolver.resolve(query_string, entities)

    def get_upstream_dependents(
        self,
        entity_query: str,
        entities: Dict[str, SnapshotEntityFact],
        relationships: List[SnapshotRelationshipFact],
        max_depth: int = 5,
        allowed_rel_types: Optional[Set[str]] = None,
    ) -> ArchitectureQueryResult:
        res = self.resolve_entity(entity_query, entities)
        if res.status != EntityResolutionStatus.RESOLVED or not res.entity:
            return self._build_unresolved_result(QueryType.UPSTREAM_DEPENDENTS, entity_query, res)

        paths, evidence = self.traversal_engine.traverse(
            start_entity=res.entity.qualified_name,
            direction="upstream",
            relationships=relationships,
            entities=entities,
            allowed_rel_types=allowed_rel_types,
            max_depth=max_depth,
        )

        explanation = self.explanation_builder.explain_paths(
            source=res.entity.qualified_name,
            target=None,
            paths=paths,
            query_type="upstream_dependents",
        )

        confidence = self._determine_overall_confidence(paths)

        return ArchitectureQueryResult(
            query_type=QueryType.UPSTREAM_DEPENDENTS,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            resolved_entity=res.entity,
            paths=paths,
            evidence=evidence,
            explanation=explanation,
            confidence=confidence,
        )

    def get_downstream_dependencies(
        self,
        entity_query: str,
        entities: Dict[str, SnapshotEntityFact],
        relationships: List[SnapshotRelationshipFact],
        max_depth: int = 5,
        allowed_rel_types: Optional[Set[str]] = None,
    ) -> ArchitectureQueryResult:
        res = self.resolve_entity(entity_query, entities)
        if res.status != EntityResolutionStatus.RESOLVED or not res.entity:
            return self._build_unresolved_result(QueryType.DOWNSTREAM_DEPENDENCIES, entity_query, res)

        paths, evidence = self.traversal_engine.traverse(
            start_entity=res.entity.qualified_name,
            direction="downstream",
            relationships=relationships,
            entities=entities,
            allowed_rel_types=allowed_rel_types,
            max_depth=max_depth,
        )

        explanation = self.explanation_builder.explain_paths(
            source=res.entity.qualified_name,
            target=None,
            paths=paths,
            query_type="downstream_dependencies",
        )

        confidence = self._determine_overall_confidence(paths)

        return ArchitectureQueryResult(
            query_type=QueryType.DOWNSTREAM_DEPENDENCIES,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            resolved_entity=res.entity,
            paths=paths,
            evidence=evidence,
            explanation=explanation,
            confidence=confidence,
        )

    def find_dependency_path(
        self,
        source_query: str,
        target_query: str,
        entities: Dict[str, SnapshotEntityFact],
        relationships: List[SnapshotRelationshipFact],
        max_depth: int = 5,
        allowed_rel_types: Optional[Set[str]] = None,
    ) -> ArchitectureQueryResult:
        src_res = self.resolve_entity(source_query, entities)
        tgt_res = self.resolve_entity(target_query, entities)

        if src_res.status != EntityResolutionStatus.RESOLVED or not src_res.entity:
            return self._build_unresolved_result(QueryType.DEPENDENCY_PATH, source_query, src_res)
        if tgt_res.status != EntityResolutionStatus.RESOLVED or not tgt_res.entity:
            return self._build_unresolved_result(QueryType.DEPENDENCY_PATH, target_query, tgt_res)

        paths, evidence, warnings = self.path_finder.find_paths(
            source=src_res.entity.qualified_name,
            target=tgt_res.entity.qualified_name,
            relationships=relationships,
            entities=entities,
            allowed_rel_types=allowed_rel_types,
            max_depth=max_depth,
        )

        explanation = self.explanation_builder.explain_paths(
            source=src_res.entity.qualified_name,
            target=tgt_res.entity.qualified_name,
            paths=paths,
            query_type="dependency_path",
        )

        confidence = self._determine_overall_confidence(paths) if paths else ResolutionConfidence.UNRESOLVED

        return ArchitectureQueryResult(
            query_type=QueryType.DEPENDENCY_PATH,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            resolved_entity=src_res.entity,
            target_resolved_entity=tgt_res.entity,
            paths=paths,
            evidence=evidence,
            explanation=explanation,
            confidence=confidence,
            warnings=warnings,
        )

    def trace_http_architecture(
        self,
        start_entity_query: str,
        entities: Dict[str, SnapshotEntityFact],
        relationships: List[SnapshotRelationshipFact],
        max_depth: int = 5,
    ) -> ArchitectureQueryResult:
        res = self.resolve_entity(start_entity_query, entities)
        if res.status != EntityResolutionStatus.RESOLVED or not res.entity:
            return self._build_unresolved_result(QueryType.HTTP_ARCHITECTURE_PATH, start_entity_query, res)

        paths, evidence, warnings = self.path_finder.trace_http_architecture(
            start_entity=res.entity.qualified_name,
            relationships=relationships,
            entities=entities,
            max_depth=max_depth,
        )

        explanation = self.explanation_builder.explain_paths(
            source=res.entity.qualified_name,
            target=None,
            paths=paths,
            query_type="http_architecture_path",
        )

        confidence = self._determine_overall_confidence(paths)

        return ArchitectureQueryResult(
            query_type=QueryType.HTTP_ARCHITECTURE_PATH,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            resolved_entity=res.entity,
            paths=paths,
            evidence=evidence,
            explanation=explanation,
            confidence=confidence,
            warnings=warnings,
        )

    def explain_risk(
        self,
        entity_query: str,
        entities: Dict[str, SnapshotEntityFact],
        risk_fact: ChangeRiskFact,
        regressions: List[ArchitectureRegression],
    ) -> ArchitectureQueryResult:
        res = self.resolve_entity(entity_query, entities)
        ent_name = res.entity.qualified_name if res.entity else entity_query

        explanation, evidence = self.explanation_builder.explain_risk(
            entity=ent_name,
            risk=risk_fact,
            regressions=regressions,
        )

        return ArchitectureQueryResult(
            query_type=QueryType.EXPLAIN_RISK,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            resolved_entity=res.entity,
            evidence=evidence,
            explanation=explanation,
            confidence=ResolutionConfidence.EXACT,
            data={"risk_level": risk_fact.risk_level.value, "score": risk_fact.score},
        )

    def explain_violation(
        self,
        violation: ArchitectureViolation,
    ) -> ArchitectureQueryResult:
        explanation, evidence = self.explanation_builder.explain_violation(violation)
        return ArchitectureQueryResult(
            query_type=QueryType.EXPLAIN_VIOLATION,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            evidence=evidence,
            explanation=explanation,
            confidence=ResolutionConfidence.EXACT if violation.resolution == "exact" else ResolutionConfidence.INFERRED,
            data={"violation_type": violation.violation_type, "severity": violation.severity},
        )

    def explain_cycle(
        self,
        cycle: ArchitectureCycle,
    ) -> ArchitectureQueryResult:
        explanation, evidence = self.explanation_builder.explain_cycle(cycle)
        return ArchitectureQueryResult(
            query_type=QueryType.EXPLAIN_CYCLE,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            evidence=evidence,
            explanation=explanation,
            confidence=ResolutionConfidence.EXACT,
            data={"cycle_id": cycle.cycle_id, "members": cycle.members, "severity": cycle.severity},
        )

    def explain_hotspot(
        self,
        hotspot: HotspotFact,
    ) -> ArchitectureQueryResult:
        explanation, evidence = self.explanation_builder.explain_hotspot(hotspot)
        return ArchitectureQueryResult(
            query_type=QueryType.EXPLAIN_HOTSPOT,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            evidence=evidence,
            explanation=explanation,
            confidence=ResolutionConfidence.EXACT,
            data={"fan_in": hotspot.fan_in, "fan_out": hotspot.fan_out, "percentile": hotspot.percentile},
        )

    def explain_orphan(
        self,
        orphan: OrphanFact,
    ) -> ArchitectureQueryResult:
        explanation, evidence = self.explanation_builder.explain_orphan(orphan)
        return ArchitectureQueryResult(
            query_type=QueryType.EXPLAIN_ORPHAN,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            evidence=evidence,
            explanation=explanation,
            confidence=ResolutionConfidence.EXACT,
            data={"exclusions_checked": orphan.exclusions_checked},
        )

    def get_entity_history(
        self,
        entity_query: str,
        evolution_result: EvolutionAnalysisResult,
    ) -> ArchitectureQueryResult:
        history, evidence, explanation = self.history_service.get_entity_history(
            entity_name=entity_query,
            evolution_result=evolution_result,
        )
        return ArchitectureQueryResult(
            query_type=QueryType.ENTITY_HISTORY,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            history=history,
            evidence=evidence,
            explanation=explanation,
            confidence=ResolutionConfidence.EXACT,
        )

    def find_issue_origin(
        self,
        issue_type: str,
        issue_key: str,
        snapshot_history: List[Tuple[str, ArchitectureAnalysisResult]],
    ) -> ArchitectureQueryResult:
        origin_snap, history, evidence, explanation = self.history_service.find_issue_origin(
            issue_type=issue_type,
            issue_key=issue_key,
            snapshot_history=snapshot_history,
        )
        return ArchitectureQueryResult(
            query_type=QueryType.ISSUE_ORIGIN,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            history=history,
            evidence=evidence,
            explanation=explanation,
            confidence=ResolutionConfidence.EXACT if origin_snap else ResolutionConfidence.UNRESOLVED,
            data={"origin_snapshot_id": origin_snap},
        )

    def execute(
        self,
        query: ArchitectureQuery,
        entities: Dict[str, SnapshotEntityFact],
        relationships: List[SnapshotRelationshipFact],
        arch_result: Optional[ArchitectureAnalysisResult] = None,
        evolution_result: Optional[EvolutionAnalysisResult] = None,
        snapshot_history: Optional[List[Tuple[str, ArchitectureAnalysisResult]]] = None,
    ) -> ArchitectureQueryResult:
        """
        Generic query execution dispatcher.
        """
        if query.query_type == QueryType.UPSTREAM_DEPENDENTS:
            return self.get_upstream_dependents(
                entity_query=query.entity or "",
                entities=entities,
                relationships=relationships,
                max_depth=query.max_depth,
                allowed_rel_types=set(query.relationship_types) if query.relationship_types else None,
            )

        elif query.query_type == QueryType.DOWNSTREAM_DEPENDENCIES:
            return self.get_downstream_dependencies(
                entity_query=query.entity or "",
                entities=entities,
                relationships=relationships,
                max_depth=query.max_depth,
                allowed_rel_types=set(query.relationship_types) if query.relationship_types else None,
            )

        elif query.query_type == QueryType.DEPENDENCY_PATH:
            return self.find_dependency_path(
                source_query=query.entity or "",
                target_query=query.target_entity or "",
                entities=entities,
                relationships=relationships,
                max_depth=query.max_depth,
                allowed_rel_types=set(query.relationship_types) if query.relationship_types else None,
            )

        elif query.query_type == QueryType.HTTP_ARCHITECTURE_PATH:
            return self.trace_http_architecture(
                start_entity_query=query.entity or "",
                entities=entities,
                relationships=relationships,
                max_depth=query.max_depth,
            )

        elif query.query_type == QueryType.EXPLAIN_RISK:
            if evolution_result and evolution_result.risk:
                return self.explain_risk(
                    entity_query=query.entity or "",
                    entities=entities,
                    risk_fact=evolution_result.risk,
                    regressions=evolution_result.regressions,
                )
            return self._build_error_result(query.query_type, "Evolution analysis result required for explain_risk query.")

        elif query.query_type == QueryType.ENTITY_HISTORY:
            if evolution_result:
                return self.get_entity_history(
                    entity_query=query.entity or "",
                    evolution_result=evolution_result,
                )
            return self._build_error_result(query.query_type, "Evolution analysis result required for entity_history query.")

        elif query.query_type == QueryType.ISSUE_ORIGIN:
            issue_type = query.params.get("issue_type", "cycle")
            issue_key = query.params.get("issue_key", query.entity or "")
            if snapshot_history:
                return self.find_issue_origin(
                    issue_type=issue_type,
                    issue_key=issue_key,
                    snapshot_history=snapshot_history,
                )
            return self._build_error_result(query.query_type, "Snapshot history required for issue_origin query.")

        return self._build_error_result(query.query_type, f"Unsupported query type '{query.query_type}'.")

    def _determine_overall_confidence(self, paths: List[TraversalPath]) -> ResolutionConfidence:
        if not paths:
            return ResolutionConfidence.EXACT
        if any(p.confidence == ResolutionConfidence.INFERRED for p in paths):
            return ResolutionConfidence.INFERRED
        return ResolutionConfidence.EXACT

    def _build_unresolved_result(
        self,
        query_type: QueryType,
        query_str: str,
        res: EntityResolutionResult,
    ) -> ArchitectureQueryResult:
        return ArchitectureQueryResult(
            query_type=query_type,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            resolved_entity=None,
            paths=[],
            evidence=[],
            explanation=Explanation(
                summary=f"Entity '{query_str}' could not be resolved.",
                detailed_reasons=[res.message],
            ),
            confidence=ResolutionConfidence.UNRESOLVED,
            warnings=[res.message],
        )

    def _build_error_result(self, query_type: QueryType, message: str) -> ArchitectureQueryResult:
        return ArchitectureQueryResult(
            query_type=query_type,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            resolved_entity=None,
            paths=[],
            evidence=[],
            explanation=Explanation(summary="Query execution error.", detailed_reasons=[message]),
            confidence=ResolutionConfidence.UNRESOLVED,
            warnings=[message],
        )
