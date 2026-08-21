"""
Architecture Evolution Service (Slice ML-12)

Main orchestration service for Architecture Evolution & Change Intelligence:
  1. Snapshot Differ (Entities, Relationships, Resolution changes)
  2. Semantic Architecture Change Analysis (Roles, Layers, Endpoints, Dependencies)
  3. Architecture Regression Analysis (New Cycles, Violations, Hotspot Growth, New Orphans)
  4. Change Impact & Risk Evaluation (Blast radius, High/Med/Low risk classification)
  5. Multi-Snapshot Evolution Trend Analysis
  6. Neo4j Graph Persistence with Strict Snapshot & Repository Isolation
"""

from typing import List, Dict, Optional, Set, Tuple, Any
import structlog

from archon.db.neo4j import neo4j_driver
from archon.pipeline.parsers.base import ParsedFile
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import ArchitectureAnalysisResult, ArchitectureNodeFact
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
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
from archon.pipeline.evolution.regressions import ArchitectureRegressionAnalyzer
from archon.pipeline.evolution.impact import ChangeImpactAnalyzer
from archon.pipeline.evolution.trends import EvolutionTrendAnalyzer

logger = structlog.get_logger(__name__)


class ArchitectureEvolutionService:
    """
    Orchestrates temporal analysis and evolution intelligence across snapshots.
    """

    def __init__(self, repository_id: str, baseline_snapshot_id: str, target_snapshot_id: str):
        self.repository_id = str(repository_id)
        self.baseline_snapshot_id = str(baseline_snapshot_id)
        self.target_snapshot_id = str(target_snapshot_id)

        self.differ = SnapshotDiffer(self.repository_id, self.baseline_snapshot_id, self.target_snapshot_id)
        self.change_analyzer = ArchitectureChangeAnalyzer(self.repository_id, self.baseline_snapshot_id, self.target_snapshot_id)
        self.regression_analyzer = ArchitectureRegressionAnalyzer(self.repository_id, self.baseline_snapshot_id, self.target_snapshot_id)
        self.impact_analyzer = ChangeImpactAnalyzer(self.repository_id, self.baseline_snapshot_id, self.target_snapshot_id)
        self.trend_analyzer = EvolutionTrendAnalyzer()

    def compare_snapshots(
        self,
        baseline_entities: Dict[str, SnapshotEntityFact],
        target_entities: Dict[str, SnapshotEntityFact],
        baseline_relationships: List[SnapshotRelationshipFact],
        target_relationships: List[SnapshotRelationshipFact],
        baseline_arch: Optional[ArchitectureAnalysisResult] = None,
        target_arch: Optional[ArchitectureAnalysisResult] = None,
        snapshot_history: Optional[List[Tuple[str, ArchitectureAnalysisResult]]] = None,
    ) -> EvolutionAnalysisResult:
        """
        Runs complete deterministic comparison between baseline and target snapshots.
        """
        # 1. Raw Snapshot Diff
        diff = self.differ.diff_snapshots(
            baseline_entities=baseline_entities,
            target_entities=target_entities,
            baseline_relationships=baseline_relationships,
            target_relationships=target_relationships,
        )

        # 2. Semantic Architectural Changes
        arch_changes = self.change_analyzer.analyze_changes(diff)

        # 3. Newly Introduced Regressions
        regressions = self.regression_analyzer.analyze_regressions(
            diff=diff,
            baseline_arch=baseline_arch,
            target_arch=target_arch,
        )

        # 4. Impact & Risk Analysis
        impact_facts, risk_fact = self.impact_analyzer.analyze_impact_and_risk(
            diff=diff,
            regressions=regressions,
            target_arch=target_arch,
        )

        # 5. Multi-Snapshot Trends (if history provided)
        trends = []
        if snapshot_history:
            trends = self.trend_analyzer.analyze_trends(snapshot_history)

        summary = {
            "added_entities_count": len(diff.added_entities),
            "removed_entities_count": len(diff.removed_entities),
            "modified_entities_count": len(diff.modified_entities),
            "added_relationships_count": len(diff.added_relationships),
            "removed_relationships_count": len(diff.removed_relationships),
            "architecture_changes_count": len(arch_changes),
            "regressions_count": len(regressions),
            "risk_level": risk_fact.risk_level.value,
            "risk_score": risk_fact.score,
        }

        return EvolutionAnalysisResult(
            repository_id=self.repository_id,
            baseline_snapshot_id=self.baseline_snapshot_id,
            target_snapshot_id=self.target_snapshot_id,
            diff=diff,
            architecture_changes=arch_changes,
            regressions=regressions,
            impact_facts=impact_facts,
            risk=risk_fact,
            trends=trends,
            summary=summary,
        )

    @staticmethod
    def build_snapshot_facts(
        repository_id: str,
        snapshot_id: str,
        parsed_files: List[ParsedFile],
        resolved_facts: List[ResolutionResult],
        arch_result: Optional[ArchitectureAnalysisResult] = None,
    ) -> Tuple[Dict[str, SnapshotEntityFact], List[SnapshotRelationshipFact]]:
        """
        Helper utility to construct SnapshotEntityFact and SnapshotRelationshipFact
        from parsed files, resolution results, and ML-11 architecture facts.
        """
        entities: Dict[str, SnapshotEntityFact] = {}
        relationships: List[SnapshotRelationshipFact] = []

        node_facts = arch_result.nodes if arch_result else {}

        # 1. Extract Classes and Functions
        for pfile in parsed_files:
            for cls in pfile.classes:
                node_fact = node_facts.get(cls.qualified_name)
                role = node_fact.architecture_role.value if node_fact else "unknown"
                layer = node_fact.layer.value if node_fact else "unknown"

                entities[cls.qualified_name] = SnapshotEntityFact(
                    qualified_name=cls.qualified_name,
                    entity_kind="Class",
                    repository_id=repository_id,
                    snapshot_id=snapshot_id,
                    module_name=pfile.module_name,
                    file_path=pfile.path,
                    architecture_role=role,
                    architecture_layer=layer,
                )

            for func in pfile.functions:
                node_fact = node_facts.get(func.qualified_name)
                role = node_fact.architecture_role.value if node_fact else "unknown"
                layer = node_fact.layer.value if node_fact else "unknown"

                entities[func.qualified_name] = SnapshotEntityFact(
                    qualified_name=func.qualified_name,
                    entity_kind="Function",
                    repository_id=repository_id,
                    snapshot_id=snapshot_id,
                    module_name=pfile.module_name,
                    file_path=pfile.path,
                    architecture_role=role,
                    architecture_layer=layer,
                )

        # 2. Extract Endpoints from resolution results
        for rel in resolved_facts:
            if rel.relationship == "REQUESTS" and rel.target_id.startswith("endpoint:"):
                entities[rel.target_id] = SnapshotEntityFact(
                    qualified_name=rel.target_id,
                    entity_kind="Endpoint",
                    repository_id=repository_id,
                    snapshot_id=snapshot_id,
                )
            elif rel.relationship == "HANDLED_BY" and rel.source_id.startswith("endpoint:"):
                entities[rel.source_id] = SnapshotEntityFact(
                    qualified_name=rel.source_id,
                    entity_kind="Endpoint",
                    repository_id=repository_id,
                    snapshot_id=snapshot_id,
                )

            relationships.append(SnapshotRelationshipFact(
                source_id=rel.source_id,
                relationship_type=rel.relationship,
                target_id=rel.target_id,
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                resolution=rel.resolution,
                evidence_type=rel.evidence_type,
            ))

        return entities, relationships

    async def persist_to_graph(self, result: EvolutionAnalysisResult):
        """
        Persists Evolution facts (Changes, Regressions, Risk) to Neo4j with snapshot isolation.
        """
        async with neo4j_driver.session() as session:
            # 1. Persist Changes
            for ch in result.architecture_changes:
                await session.run(
                    """
                    MERGE (c:ArchitectureChange {
                        change_id: $change_id,
                        repository_id: $repo_id,
                        baseline_snapshot_id: $base_id,
                        target_snapshot_id: $tgt_id
                    })
                    SET c.category = $category,
                        c.entity_id = $entity_id,
                        c.description = $desc
                    WITH c
                    MATCH (node {qualified_name: $entity_id, repository_id: $repo_id, snapshot_id: $tgt_id})
                    MERGE (node)-[:HAS_CHANGE]->(c)
                    """,
                    change_id=ch.change_id,
                    repo_id=self.repository_id,
                    base_id=self.baseline_snapshot_id,
                    tgt_id=self.target_snapshot_id,
                    category=ch.category,
                    entity_id=ch.entity_id,
                    desc=ch.description,
                )

            # 2. Persist Regressions
            for reg in result.regressions:
                await session.run(
                    """
                    MERGE (r:ArchitectureRegression {
                        regression_id: $reg_id,
                        repository_id: $repo_id,
                        baseline_snapshot_id: $base_id,
                        target_snapshot_id: $tgt_id
                    })
                    SET r.regression_type = $reg_type,
                        r.severity = $severity,
                        r.affected_entity = $affected,
                        r.message = $msg
                    """,
                    reg_id=reg.regression_id,
                    repo_id=self.repository_id,
                    base_id=self.baseline_snapshot_id,
                    tgt_id=self.target_snapshot_id,
                    reg_type=reg.regression_type.value,
                    severity=reg.severity,
                    affected=reg.affected_entity,
                    msg=reg.message,
                )

            # 3. Persist Risk Evaluation
            if result.risk:
                await session.run(
                    """
                    MERGE (k:ChangeRisk {
                        repository_id: $repo_id,
                        baseline_snapshot_id: $base_id,
                        target_snapshot_id: $tgt_id
                    })
                    SET k.risk_level = $level,
                        k.score = $score,
                        k.reasons = $reasons
                    """,
                    repo_id=self.repository_id,
                    base_id=self.baseline_snapshot_id,
                    tgt_id=self.target_snapshot_id,
                    level=result.risk.risk_level.value,
                    score=result.risk.score,
                    reasons=result.risk.reasons,
                )
