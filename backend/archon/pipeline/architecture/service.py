"""
Architecture Intelligence Service (Slice ML-11)

Coordinates the complete architectural analysis pipeline:
  1. Architecture Classifier (Role & Layer mapping)
  2. Boundary Analysis & Layer Transitions
  3. Circular Dependency Detection
  4. Graph-Topology Hotspot Analysis
  5. Candidate Orphan Analysis
  6. Architecture Violation Detection
  7. Graph Persistence (HAS_ROLE, IN_LAYER, ARCHITECTURE_VIOLATION)
"""

from typing import List, Dict, Optional, Set, Any
import structlog

from archon.db.neo4j import neo4j_driver
from archon.pipeline.parsers.base import ParsedFile
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import (
    ArchitectureRole,
    ArchitectureLayer,
    ArchitectureNodeFact,
    ArchitectureCycle,
    HotspotFact,
    OrphanFact,
    ArchitectureViolation,
    ArchitectureAnalysisResult,
)
from archon.pipeline.architecture.classifier import ArchitectureClassifier
from archon.pipeline.architecture.cycles import CycleDetector
from archon.pipeline.architecture.hotspots import HotspotAnalyzer
from archon.pipeline.architecture.orphans import OrphanAnalyzer
from archon.pipeline.architecture.violations import ArchitectureViolationAnalyzer

logger = structlog.get_logger(__name__)


class ArchitectureIntelligenceService:
    """
    Main orchestration service for Slice ML-11 Architecture Intelligence.
    """

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

        self.classifier = ArchitectureClassifier(self.repository_id, self.snapshot_id)
        self.cycle_detector = CycleDetector(self.repository_id, self.snapshot_id)
        self.hotspot_analyzer = HotspotAnalyzer(self.repository_id, self.snapshot_id)
        self.orphan_analyzer = OrphanAnalyzer(self.repository_id, self.snapshot_id)
        self.violation_analyzer = ArchitectureViolationAnalyzer(self.repository_id, self.snapshot_id)

    def analyze(
        self,
        parsed_files: List[ParsedFile],
        resolved_facts: List[ResolutionResult],
        file_contents: Optional[Dict[str, str]] = None,
        di_bindings: Optional[Dict[str, str]] = None
    ) -> ArchitectureAnalysisResult:
        """
        Executes deterministic, snapshot-scoped architectural analysis.
        """
        # 1. Classify nodes into Roles & Layers
        node_facts = self.classifier.classify_repository(parsed_files, resolved_facts, file_contents=file_contents)

        # 2. Detect circular dependencies
        cycles = self.cycle_detector.detect_cycles(resolved_facts)

        # 3. Detect hotspots
        hotspots = self.hotspot_analyzer.analyze_hotspots(node_facts, resolved_facts)

        # 4. Detect candidate orphans
        di_types = set(di_bindings.values()) if di_bindings else set()
        orphans = self.orphan_analyzer.analyze_orphans(node_facts, resolved_facts, di_bound_types=di_types)

        # 5. Detect architectural rule violations
        violations = self.violation_analyzer.analyze_violations(
            node_facts=node_facts,
            resolved_facts=resolved_facts,
            cycles=cycles,
            di_bindings=di_bindings
        )

        summary = {
            "total_nodes": len(node_facts),
            "controllers": sum(1 for f in node_facts.values() if f.architecture_role == ArchitectureRole.CONTROLLER),
            "services": sum(1 for f in node_facts.values() if f.architecture_role == ArchitectureRole.SERVICE),
            "repositories": sum(1 for f in node_facts.values() if f.architecture_role == ArchitectureRole.REPOSITORY),
            "components": sum(1 for f in node_facts.values() if f.architecture_role == ArchitectureRole.COMPONENT),
            "clients": sum(1 for f in node_facts.values() if f.architecture_role == ArchitectureRole.CLIENT),
            "unknown": sum(1 for f in node_facts.values() if f.architecture_role == ArchitectureRole.UNKNOWN),
            "cycles_count": len(cycles),
            "hotspots_count": len(hotspots),
            "orphans_count": len(orphans),
            "violations_count": len(violations),
        }

        return ArchitectureAnalysisResult(
            nodes=node_facts,
            cycles=cycles,
            hotspots=hotspots,
            orphans=orphans,
            violations=violations,
            summary=summary
        )

    async def persist_to_graph(self, result: ArchitectureAnalysisResult):
        """
        Persists HAS_ROLE, IN_LAYER, and ARCHITECTURE_VIOLATION edges to Neo4j.
        Idempotent MERGE ensures rerun safety.
        """
        async with neo4j_driver.session() as session:
            # 1. Persist Roles & Layers
            for qname, fact in result.nodes.items():
                if fact.architecture_role != ArchitectureRole.UNKNOWN:
                    # Role Node & Edge
                    await session.run(
                        """
                        MERGE (role:ArchitectureRole {name: $role_name, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        WITH role
                        MATCH (node {qualified_name: $qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (node)-[r:HAS_ROLE]->(role)
                        SET r.resolution = $resolution,
                            r.evidence_type = $evidence_type,
                            r.evidence = $evidence,
                            r.repository_id = $repo_id,
                            r.snapshot_id = $snapshot_id
                        """,
                        repo_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        qname=qname,
                        role_name=fact.architecture_role.value,
                        resolution=fact.resolution,
                        evidence_type=fact.evidence_type,
                        evidence=fact.evidence
                    )

                if fact.layer != ArchitectureLayer.UNKNOWN:
                    # Layer Node & Edge
                    await session.run(
                        """
                        MERGE (layer:ArchitectureLayer {name: $layer_name, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        WITH layer
                        MATCH (node {qualified_name: $qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (node)-[r:IN_LAYER]->(layer)
                        SET r.resolution = $resolution,
                            r.evidence_type = $evidence_type,
                            r.repository_id = $repo_id,
                            r.snapshot_id = $snapshot_id
                        """,
                        repo_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        qname=qname,
                        layer_name=fact.layer.value,
                        resolution=fact.resolution,
                        evidence_type=fact.evidence_type
                    )

            # 2. Persist Violations
            for v in result.violations:
                await session.run(
                    """
                    MATCH (source {qualified_name: $src_qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MATCH (target {qualified_name: $tgt_qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (source)-[r:ARCHITECTURE_VIOLATION {
                        violation_type: $vtype,
                        repository_id: $repo_id,
                        snapshot_id: $snapshot_id
                    }]->(target)
                    SET r.severity = $severity,
                        r.resolution = $resolution,
                        r.evidence_type = $evidence_type,
                        r.message = $message,
                        r.source_layer = $src_layer,
                        r.target_layer = $tgt_layer,
                        r.repository_id = $repo_id,
                        r.snapshot_id = $snapshot_id
                    """,
                    repo_id=self.repository_id,
                    snapshot_id=self.snapshot_id,
                    src_qname=v.source_qualified_name,
                    tgt_qname=v.target_qualified_name,
                    vtype=v.violation_type,
                    severity=v.severity,
                    resolution=v.resolution,
                    evidence_type=v.evidence_type,
                    message=v.message,
                    src_layer=v.source_layer,
                    tgt_layer=v.target_layer
                )
