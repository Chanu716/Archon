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
        # Aggregates from health and graph
        # Wait, to get callers/callees accurately, we can query GraphService, or we can use fan_in/fan_out from health if they exist.
        fan_in = health.metrics.get("incoming_coupling") or health.metrics.get("fan_in")
        fan_out = health.metrics.get("outgoing_coupling") or health.metrics.get("fan_out")
        
        churn_val = None
        # We can fetch churn directly if it's a file, but since this is just an overview,
        # we can lazy-load it, or try to get it if the metric 'churn' exists.
        
        return EntityOverview(
            complexity=health.metrics.get("cyclomatic_complexity"),
            coupling=health.metrics.get("outgoing_coupling") or health.metrics.get("coupling"),
            risk=health.metrics.get("risk_score"),
            callers=int(fan_in) if fan_in is not None else None,
            callees=int(fan_out) if fan_out is not None else None,
            churn=churn_val # We'll populate churn when we load GitContext or if we fetch it here.
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
        impact_svc = ImpactService(context.repository_id, context.snapshot_id)
        # analyze_impact takes a qualified_name or path.
        lookup = context.qualified_name or context.file_path
        
        if not lookup:
            return ImpactContext(graph={"nodes": [], "edges": []})
            
        data = await impact_svc.analyze_impact(lookup, max_depth=3)
        
        return ImpactContext(
            direct_callers=data["summary"]["direct_callers"],
            indirect_callers=data["summary"]["indirect_callers"],
            direct_callees=data["summary"]["direct_callees"],
            indirect_callees=data["summary"]["indirect_callees"],
            affected_entities=data["summary"]["affected_entities"],
            graph=data["graph"]
        )

    async def get_evolution(self, context: InvestigationContext) -> EvolutionContext:
        evo_svc = EvolutionService(self.db, context.repository_id)
        # We need timeline
        timeline = await evo_svc.get_timeline()
        if not timeline:
            return EvolutionContext()
            
        # Try to compare with previous snapshot
        current_idx = next((i for i, node in enumerate(timeline) if node.snapshot_id == context.snapshot_id), -1)
        if current_idx < 0:
            return EvolutionContext()
            
        # Trend
        if current_idx < len(timeline) - 1:
            prev_snapshot_id = timeline[current_idx + 1].snapshot_id
            try:
                comp = await evo_svc.compare_snapshots(prev_snapshot_id, context.snapshot_id)
                # Filter for this entity
                lookup = context.qualified_name or context.file_path
                if not lookup:
                    return EvolutionContext()
                    
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
                return EvolutionContext()
        else:
            # First snapshot, no previous to compare
            return EvolutionContext()

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
