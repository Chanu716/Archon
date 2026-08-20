import uuid
import ast
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog
from fastapi import HTTPException

from archon.models.investigation import (
    InvestigationContext, EntityOverview, CodeContext, GraphContext,
    HealthContext, GitContext, ImpactContext, EvolutionContext,
    SemanticContext, InvestigationBaseResponse
)
from archon.models.repository import AnalysisSnapshot
from archon.models.metrics import EntityMetric
from archon.models.git import GitFileChurn, GitCommit, GitFileChange

from archon.services.graph_service import GraphService
from archon.services.impact_service import ImpactService
from archon.services.evolution_service import EvolutionService
from archon.services.semantic_search import SemanticSearchService
from archon.services.storage_service import RepositoryStorageService
from archon.services.tools import _extract_ast_node

logger = structlog.get_logger(__name__)

class InvestigationService:
    def __init__(self, db: AsyncSession, repository_id: uuid.UUID):
        self.db = db
        self.repository_id = repository_id
        self.storage = RepositoryStorageService()

    async def _resolve_snapshot_id(self, snapshot_id: Optional[uuid.UUID] = None) -> uuid.UUID:
        if snapshot_id:
            return snapshot_id
            
        result = await self.db.execute(
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.repository_id == self.repository_id)
            .where(AnalysisSnapshot.is_latest == True)
            .order_by(AnalysisSnapshot.analyzed_at.desc())
        )
        snapshot = result.scalars().first()
        if not snapshot:
            raise HTTPException(status_code=404, detail="No snapshot found for repository")
        return snapshot.id

    async def get_context(self, entity_id: str, snapshot_id: Optional[uuid.UUID] = None) -> InvestigationContext:
        resolved_snap_id = await self._resolve_snapshot_id(snapshot_id)
        graph = GraphService(self.repository_id, resolved_snap_id)
        
        node = await graph.get_node_details(entity_id)
        if not node:
            raise HTTPException(status_code=404, detail="Entity not found in graph")
            
        n_data = node["data"]
        qname = n_data.get("qualified_name")
        path = n_data.get("path")
        e_type = n_data.get("type")
        e_name = n_data.get("name") or n_data.get("label") or qname
        
        # If path is not set on node, resolve containing file path from Neo4j
        if not path:
            from archon.db.neo4j import neo4j_driver
            try:
                async with neo4j_driver.session() as session:
                    res = await session.run("""
                    MATCH (n {snapshot_id: $snapshot_id})
                    WHERE elementId(n) = $entity_id OR n.qualified_name = $entity_id OR n.name = $entity_id
                    OPTIONAL MATCH (f:File {snapshot_id: $snapshot_id})-[:CONTAINS*1..2]->(n)
                    RETURN coalesce(n.path, f.path) as resolved_path
                    LIMIT 1
                    """, snapshot_id=str(resolved_snap_id), entity_id=entity_id)
                    rec = await res.single()
                    if rec and rec["resolved_path"]:
                        path = rec["resolved_path"]
            except Exception:
                pass

        return InvestigationContext(
            repository_id=self.repository_id,
            snapshot_id=resolved_snap_id,
            entity_id=entity_id,
            entity_name=e_name,
            qualified_name=qname,
            entity_type=e_type,
            file_path=path
        )

    async def get_health(self, context: InvestigationContext) -> HealthContext:
        if not context.qualified_name and not context.file_path:
            return HealthContext(metrics={}, sources={})
            
        entity_name_lookup = context.qualified_name or context.file_path
        
        metrics_result = await self.db.execute(
            select(EntityMetric)
            .where(EntityMetric.snapshot_id == context.snapshot_id)
            .where(EntityMetric.entity_name == entity_name_lookup)
            .where(EntityMetric.entity_type == context.entity_type)
        )
        metrics = metrics_result.scalars().all()
        
        formatted = {m.metric_name: m.metric_value for m in metrics}
        sources = {m.metric_name: m.metric_source for m in metrics}
        
        return HealthContext(metrics=formatted, sources=sources)

    async def get_overview(self, context: InvestigationContext, health: HealthContext) -> EntityOverview:
        fan_in = health.metrics.get("incoming_coupling") or health.metrics.get("fan_in")
        fan_out = health.metrics.get("outgoing_coupling") or health.metrics.get("fan_out")
        complexity = health.metrics.get("cyclomatic_complexity")
        coupling = health.metrics.get("outgoing_coupling") or health.metrics.get("coupling")
        risk = health.metrics.get("risk_score")

        # Dynamically query active graph if metrics were not pre-cached in Postgres
        if fan_in is None or fan_out is None or complexity is None:
            try:
                from archon.db.neo4j import neo4j_driver
                async with neo4j_driver.session() as session:
                    res = await session.run("""
                    MATCH (n {snapshot_id: $snapshot_id})
                    WHERE elementId(n) = $entity_id OR n.qualified_name = $entity_id OR n.name = $entity_id
                    OPTIONAL MATCH (caller)-[:CALLS|IMPORTS|DEFINES]->(n)
                    OPTIONAL MATCH (n)-[:CALLS|IMPORTS|DEFINES]->(callee)
                    RETURN count(DISTINCT caller) as fan_in,
                           count(DISTINCT callee) as fan_out,
                           coalesce(n.cyclomatic_complexity, 1) as cc,
                           coalesce(n.risk_score, 0.25) as risk
                    """, snapshot_id=str(context.snapshot_id), entity_id=context.entity_id)
                    rec = await res.single()
                    if rec:
                        if fan_in is None:
                            fan_in = rec["fan_in"]
                        if fan_out is None:
                            fan_out = rec["fan_out"]
                        if complexity is None:
                            complexity = rec["cc"]
                        if coupling is None:
                            coupling = rec["fan_out"]
                        if risk is None:
                            risk = rec["risk"]
            except Exception as e:
                logger.warning("overview_neo4j_fallback_failed", error=str(e))

        return EntityOverview(
            complexity=complexity or 1,
            coupling=coupling or 0,
            risk=round(risk or 0.15, 2),
            callers=int(fan_in) if fan_in is not None else 0,
            callees=int(fan_out) if fan_out is not None else 0,
            churn=None
        )

    async def get_code(self, context: InvestigationContext) -> Optional[CodeContext]:
        if not context.file_path:
            return None
            
        try:
            content = self.storage.get_file(context.repository_id, context.file_path)
            
            # If it's a Function or Class, try to extract its specific code block
            if context.entity_type in ["Function", "Method"]:
                extracted = _extract_ast_node(content, context.entity_name, ast.FunctionDef)
                if not extracted:
                    extracted = _extract_ast_node(content, context.entity_name, ast.AsyncFunctionDef)
                if extracted:
                    content = extracted
            elif context.entity_type == "Class":
                extracted = _extract_ast_node(content, context.entity_name, ast.ClassDef)
                if extracted:
                    content = extracted
                    
            truncated = False
            if len(content) > 3000:
                content = content[:3000]
                truncated = True
                
            return CodeContext(source_code=content, truncated=truncated)
        except Exception as e:
            logger.warning("get_code_failed", error=str(e), path=context.file_path)
            return None

    async def get_graph(self, context: InvestigationContext) -> GraphContext:
        graph_svc = GraphService(context.repository_id, context.snapshot_id)
        # expand_node gives 1-hop relationships
        data = await graph_svc.expand_node(context.entity_id)
        return GraphContext(nodes=data["nodes"], edges=data["edges"])

    async def get_base_investigation(self, entity_id: str, snapshot_id: Optional[uuid.UUID] = None) -> InvestigationBaseResponse:
        context = await self.get_context(entity_id, snapshot_id)
        health = await self.get_health(context)
        overview = await self.get_overview(context, health)
        
        # Git churn for overview (fast lookup)
        if context.file_path:
            churn_res = await self.db.execute(
                select(GitFileChurn)
                .where(GitFileChurn.snapshot_id == context.snapshot_id)
                .where(GitFileChurn.file_path == context.file_path)
            )
            churn_obj = churn_res.scalars().first()
            if churn_obj:
                overview.churn = churn_obj.churn
        
        code = await self.get_code(context)
        graph = await self.get_graph(context)
        
        return InvestigationBaseResponse(
            context=context,
            overview=overview,
            code=code,
            graph=graph,
            health=health
        )

    async def get_git(self, context: InvestigationContext) -> Optional[GitContext]:
        if not context.file_path:
            return None
            
        # Get Churn
        churn_res = await self.db.execute(
            select(GitFileChurn)
            .where(GitFileChurn.snapshot_id == context.snapshot_id)
            .where(GitFileChurn.file_path == context.file_path)
        )
        churn_obj = churn_res.scalars().first()
        
        if not churn_obj:
            return None
            
        # Get recent commits for this file
        changes_res = await self.db.execute(
            select(GitFileChange, GitCommit)
            .join(GitCommit, (GitFileChange.commit_sha == GitCommit.commit_sha) & (GitFileChange.snapshot_id == GitCommit.snapshot_id))
            .where(GitFileChange.snapshot_id == context.snapshot_id)
            .where(GitFileChange.file_path == context.file_path)
            .order_by(GitCommit.committed_at.desc())
            .limit(5)
        )
        rows = changes_res.all()
        recent_commits = []
        for change, commit in rows:
            recent_commits.append({
                "sha": commit.commit_sha,
                "author": commit.author_name,
                "message": commit.message,
                "date": commit.committed_at.isoformat(),
                "insertions": change.insertions,
                "deletions": change.deletions,
                "change_type": change.change_type
            })
            
        return GitContext(
            commit_count=churn_obj.commit_count,
            churn=churn_obj.churn,
            first_changed_at=churn_obj.first_changed_at.isoformat() if churn_obj.first_changed_at else None,
            last_changed_at=churn_obj.last_changed_at.isoformat() if churn_obj.last_changed_at else None,
            recent_commits=recent_commits
        )

    async def get_impact(self, context: InvestigationContext) -> ImpactContext:
        try:
            impact_svc = ImpactService(
                repository_id=context.repository_id,
                snapshot_id=context.snapshot_id
            )
            result = await impact_svc.analyze(context.entity_id, direction="both")
            summary = result.summary
            return ImpactContext(
                direct_callers=summary.direct_callers,
                indirect_callers=summary.indirect_callers,
                direct_callees=summary.direct_callees,
                indirect_callees=summary.indirect_callees,
                affected_entities=(
                    summary.direct_callers + summary.indirect_callers +
                    summary.direct_callees + summary.indirect_callees
                ),
                graph={"nodes": [], "edges": []}
            )
        except Exception as e:
            logger.warning("get_impact_failed", error=str(e), entity=context.entity_id)
            return ImpactContext(
                direct_callers=0, indirect_callers=0,
                direct_callees=0, indirect_callees=0,
                affected_entities=0, graph={"nodes": [], "edges": []}
            )

    async def get_evolution(self, context: InvestigationContext) -> EvolutionContext:
        try:
            evo_svc = EvolutionService(self.db, context.repository_id)
            timeline = await evo_svc.get_timeline()
            if not timeline:
                return EvolutionContext(lifecycle=None, relationship_changes=[], drift_findings=[])
                
            current_idx = next((i for i, node in enumerate(timeline) if node.snapshot_id == context.snapshot_id), -1)
            if current_idx < 0:
                return EvolutionContext(lifecycle=None, relationship_changes=[], drift_findings=[])
                
            if current_idx < len(timeline) - 1:
                prev_snapshot_id = timeline[current_idx + 1].snapshot_id
                try:
                    comp = await evo_svc.compare_snapshots(prev_snapshot_id, context.snapshot_id)
                    lookup = context.qualified_name or context.file_path
                    if not lookup:
                        return EvolutionContext(lifecycle=None, relationship_changes=[], drift_findings=[])
                        
                    lifecycle = next((e for e in comp.entities if e.qualified_name == lookup), None)
                    rels = [r for r in comp.relationships if r.source_qname == lookup or r.target_qname == lookup]
                    drifts = [d for d in comp.drift_findings if d.entity_name == lookup]
                    
                    return EvolutionContext(
                        lifecycle=lifecycle,
                        relationship_changes=rels,
                        drift_findings=drifts
                    )
                except Exception as e:
                    logger.warning("evolution_compare_failed", error=str(e))
                    return EvolutionContext(lifecycle=None, relationship_changes=[], drift_findings=[])
            else:
                return EvolutionContext(lifecycle=None, relationship_changes=[], drift_findings=[])
        except Exception as e:
            logger.warning("get_evolution_outer_failed", error=str(e))
            return EvolutionContext(lifecycle=None, relationship_changes=[], drift_findings=[])

    async def get_semantic(self, context: InvestigationContext) -> SemanticContext:
        sem_svc = SemanticSearchService(self.db)
        lookup = context.qualified_name or context.entity_name
        
        if not lookup:
            return SemanticContext(related_entities=[])
            
        results = await sem_svc.search(
            repository_id=context.repository_id,
            query=lookup,
            snapshot_id=context.snapshot_id,
            limit=5
        )
        
        # Filter self out
        related = [r for r in results if r["name"] != lookup and r["file"] != context.file_path]
        return SemanticContext(related_entities=related)
