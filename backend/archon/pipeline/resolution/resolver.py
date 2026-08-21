"""
Cross-Language Resolution Engine Coordinator (ML-4 / ML-10 / ML-11)

Coordinates deterministic module, symbol, dependency, HTTP endpoint, and
architecture intelligence resolution across all repository files and writes
resolved edges to the Neo4j architecture graph.
"""

from pathlib import Path
from typing import List, Dict, Optional
import uuid
import structlog

from archon.db.neo4j import neo4j_driver
from archon.pipeline.parsers.base import ParsedFile
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.resolution.imports import ModuleAndSymbolResolver
from archon.pipeline.resolution.dependency_resolver import DependencyAwareCallResolver
from archon.pipeline.resolution.endpoints import EndpointResolver

logger = structlog.get_logger(__name__)


class CrossLanguageResolver:
    """
    Coordinates and persists cross-language resolution and architecture facts.

    Guarantees:
      1. Snapshot isolation: all nodes and relationships carry snapshot_id.
      2. Idempotency: MERGE statements prevent duplicate relationships on reruns.
      3. Deterministic evidence: never guesses; strictly exact / inferred / unresolved.
      4. Zero code execution: strictly static analysis.
    """

    def __init__(self, repository_id: uuid.UUID, snapshot_id: uuid.UUID, target_path: Optional[Path] = None):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)
        self.target_path = target_path

        self.module_symbol_resolver = ModuleAndSymbolResolver()
        self.dependency_resolver = DependencyAwareCallResolver()
        self.endpoint_resolver = EndpointResolver()

    async def resolve_and_persist(
        self,
        parsed_files: List[ParsedFile],
        file_contents: Optional[Dict[str, str]] = None
    ) -> List[ResolutionResult]:
        """
        Runs all deterministic resolution passes and writes the resulting
        edges and Endpoint nodes to the Neo4j architecture graph.
        """
        # Load file contents from disk if not provided
        contents: Dict[str, str] = file_contents or {}
        if not contents and self.target_path and self.target_path.exists():
            for pfile in parsed_files:
                fpath = self.target_path / pfile.path
                if fpath.exists():
                    try:
                        contents[pfile.path] = fpath.read_text(encoding="utf-8", errors="replace")
                    except Exception as e:
                        logger.warning("read_file_content_error", path=pfile.path, error=str(e))

        # 1. Run Module and Symbol Resolution (ML-8 / ML-9)
        import_results = self.module_symbol_resolver.resolve(parsed_files, contents)

        # 2. Run Dependency-Aware Resolution (ML-10)
        dep_results = self.dependency_resolver.resolve(parsed_files, contents)

        # 3. Run API / HTTP Endpoint Resolution
        endpoint_results = self.endpoint_resolver.resolve(parsed_files, contents)

        all_results = import_results + dep_results + endpoint_results

        # 4. Persist resolution results to Neo4j with snapshot isolation & idempotency
        await self._persist_to_graph(all_results)

        # 5. Run Architecture Intelligence Analysis (ML-11)
        from archon.pipeline.architecture.service import ArchitectureIntelligenceService
        architecture_service = ArchitectureIntelligenceService(self.repository_id, self.snapshot_id)
        arch_result = architecture_service.analyze(
            parsed_files=parsed_files,
            resolved_facts=all_results,
            file_contents=contents
        )

        # 6. Persist Architecture Intelligence facts to Neo4j
        await architecture_service.persist_to_graph(arch_result)

        logger.info(
            "cross_language_resolution_persisted",
            total_resolved=len(all_results),
            imports_count=len(import_results),
            dependencies_count=len(dep_results),
            endpoints_count=len(endpoint_results),
            architecture_nodes_count=len(arch_result.nodes),
            violations_count=len(arch_result.violations),
            snapshot_id=self.snapshot_id
        )
        return all_results

    async def _persist_to_graph(self, results: List[ResolutionResult]):
        """Persists resolved relationships to Neo4j in an idempotent, snapshot-isolated manner."""
        async with neo4j_driver.session() as session:
            for res in results:
                # ── Case 1: Resolved Module IMPORTS ───────────────────────────
                if res.relationship == "IMPORTS":
                    await session.run(
                        """
                        MATCH (source:Module {qualified_name: $source_id, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (target:Module {qualified_name: $target_id, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (source)-[r:IMPORTS]->(target)
                        SET r.resolution = $resolution,
                            r.evidence_type = $evidence_type,
                            r.reason = $reason,
                            r.source_language = $source_lang,
                            r.target_language = $target_lang,
                            r.repository_id = $repo_id,
                            r.snapshot_id = $snapshot_id
                        """,
                        repo_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        source_id=res.source_id,
                        target_id=res.target_id,
                        resolution=res.resolution,
                        evidence_type=res.evidence_type,
                        reason=res.reason,
                        source_lang=res.source_language,
                        target_lang=res.target_language
                    )

                # ── Case 2: Resolved Function CALLS ───────────────────────────
                elif res.relationship == "CALLS":
                    await session.run(
                        """
                        MATCH (caller:Function {qualified_name: $source_id, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (callee:Function {qualified_name: $target_id, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (caller)-[r:CALLS]->(callee)
                        SET r.resolution = $resolution,
                            r.evidence_type = $evidence_type,
                            r.reason = $reason,
                            r.source_language = $source_lang,
                            r.target_language = $target_lang,
                            r.repository_id = $repo_id,
                            r.snapshot_id = $snapshot_id
                        """,
                        repo_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        source_id=res.source_id,
                        target_id=res.target_id,
                        resolution=res.resolution,
                        evidence_type=res.evidence_type,
                        reason=res.reason,
                        source_lang=res.source_language,
                        target_lang=res.target_language
                    )

                # ── Case 3: Constructor/Type DEPENDS_ON ────────────────────────
                elif res.relationship == "DEPENDS_ON":
                    await session.run(
                        """
                        MATCH (source:Class {qualified_name: $source_id, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (target:Class {qualified_name: $target_id, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (source)-[r:DEPENDS_ON]->(target)
                        SET r.resolution = $resolution,
                            r.evidence_type = $evidence_type,
                            r.reason = $reason,
                            r.dep_name = $dep_name,
                            r.repository_id = $repo_id,
                            r.snapshot_id = $snapshot_id
                        """,
                        repo_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        source_id=res.source_id,
                        target_id=res.target_id,
                        resolution=res.resolution,
                        evidence_type=res.evidence_type,
                        reason=res.reason,
                        dep_name=res.metadata.get("dep_name", "")
                    )

                # ── Case 4: Class IMPLEMENTS Interface ────────────────────────
                elif res.relationship == "IMPLEMENTS":
                    await session.run(
                        """
                        MATCH (source:Class {qualified_name: $source_id, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (target:Class {qualified_name: $target_id, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (source)-[r:IMPLEMENTS]->(target)
                        SET r.resolution = $resolution,
                            r.evidence_type = $evidence_type,
                            r.reason = $reason,
                            r.repository_id = $repo_id,
                            r.snapshot_id = $snapshot_id
                        """,
                        repo_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        source_id=res.source_id,
                        target_id=res.target_id,
                        resolution=res.resolution,
                        evidence_type=res.evidence_type,
                        reason=res.reason
                    )

                # ── Case 5: Frontend Caller Function -[:REQUESTS]-> Endpoint ──
                elif res.relationship == "REQUESTS":
                    http_method = res.metadata.get("http_method", "GET")
                    http_path = res.metadata.get("path", "")
                    await session.run(
                        """
                        MERGE (e:Endpoint {method: $method, path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        SET e.name = $method + ' ' + $path,
                            e.qualified_name = 'endpoint:' + $method + ':' + $path
                        WITH e
                        MATCH (caller:Function {qualified_name: $caller_qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (caller)-[r:REQUESTS]->(e)
                        SET r.resolution = $resolution,
                            r.http_method = $method,
                            r.path = $path,
                            r.evidence_type = $evidence_type,
                            r.reason = $reason,
                            r.source_language = $source_lang,
                            r.target_language = $target_lang,
                            r.repository_id = $repo_id,
                            r.snapshot_id = $snapshot_id
                        """,
                        repo_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        caller_qname=res.source_id,
                        method=http_method,
                        path=http_path,
                        resolution=res.resolution,
                        evidence_type=res.evidence_type,
                        reason=res.reason,
                        source_lang=res.source_language,
                        target_lang=res.target_language
                    )

                # ── Case 6: Endpoint -[:HANDLED_BY]-> Backend Handler Function ─
                elif res.relationship == "HANDLED_BY":
                    http_method = res.metadata.get("http_method", "GET")
                    http_path = res.metadata.get("path", "")
                    await session.run(
                        """
                        MERGE (e:Endpoint {method: $method, path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        SET e.name = $method + ' ' + $path,
                            e.qualified_name = 'endpoint:' + $method + ':' + $path
                        WITH e
                        MATCH (handler:Function {qualified_name: $handler_qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (e)-[r:HANDLED_BY]->(handler)
                        SET r.resolution = $resolution,
                            r.evidence_type = $evidence_type,
                            r.reason = $reason,
                            r.repository_id = $repo_id,
                            r.snapshot_id = $snapshot_id
                        """,
                        repo_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        handler_qname=res.target_id,
                        method=http_method,
                        path=http_path,
                        resolution=res.resolution,
                        evidence_type=res.evidence_type,
                        reason=res.reason
                    )
