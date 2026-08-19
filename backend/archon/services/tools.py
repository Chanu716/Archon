import ast
import uuid
from typing import Dict, Any, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from archon.pipeline.tools.registry import tool_registry
from archon.models.tools import (
    ToolResult, SearchCodeInput, GetFileInput, GetFunctionInput, 
    GetClassInput, GetGraphContextInput, GetCallersInput, 
    GetCalleesInput, GetImpactInput, GetMetricsInput, 
    GetGitContextInput, GetHotspotsInput,
    CompareSnapshotsInput, GetEvolutionTimelineInput, 
    GetDriftFindingsInput, GetMetricTrendInput
)

from archon.services.semantic_search import SemanticSearchService
from archon.services.storage_service import RepositoryStorageService
from archon.services.graph_service import GraphService
from archon.services.impact_service import ImpactService
from archon.db.neo4j import neo4j_driver
from archon.models.metrics import EntityMetric
from archon.models.git import GitFileChurn, GitCommit
from archon.models.repository import AnalysisSnapshot
from archon.pipeline.analysis.risk_calculator import classify_risk
from archon.services.evolution_service import EvolutionService
logger = structlog.get_logger(__name__)

# Constants
MAX_FILE_CHARS = 3000
MAX_GRAPH_NODES = 200

def _get_context_vars(context: Dict[str, Any]):
    return (
        context["db_session"], 
        context["repository_id"], 
        context["snapshot_id"]
    )

def _extract_ast_node(source_code: str, entity_name: str, node_type: type) -> str:
    """Extracts a specific function or class definition from source code."""
    try:
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, node_type) and node.name == entity_name:
                return ast.get_source_segment(source_code, node) or ""
    except SyntaxError:
        pass
    return ""


@tool_registry.register(
    name="search_code",
    description="Search the codebase semantically to find relevant files, functions, or classes based on a natural language query.",
    input_model=SearchCodeInput
)
async def handle_search_code(input: SearchCodeInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    service = SemanticSearchService(db)
    
    results = await service.search(
        repository_id=repo_id,
        query=input.query,
        snapshot_id=snap_id,
        limit=min(input.limit, 10)
    )
    return ToolResult(success=True, tool_name="search_code", data=results)


@tool_registry.register(
    name="get_file",
    description="Retrieve the content of a specific file. Useful when you know the exact relative path.",
    input_model=GetFileInput
)
async def handle_get_file(input: GetFileInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    storage = RepositoryStorageService()
    
    try:
        content = storage.get_file(repo_id, input.relative_path)
        truncated = False
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS]
            truncated = True
        return ToolResult(
            success=True, 
            tool_name="get_file", 
            data={"path": input.relative_path, "content": content},
            truncated=truncated
        )
    except Exception as e:
        return ToolResult(success=False, tool_name="get_file", data="", error=str(e))


async def _get_entity_source(entity_id: str, context: Dict[str, Any], entity_type: str, ast_type: type) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    graph = GraphService(repository_id=repo_id, snapshot_id=snap_id)
    storage = RepositoryStorageService()
    
    node = await graph.get_node_details(entity_id)
    if not node:
        # Fallback to search by qualified name
        nodes = await graph.search_nodes(entity_id, limit=1)
        if nodes:
            node = nodes[0]
            
    if not node:
        return ToolResult(success=False, tool_name=f"get_{entity_type}", data="", error="Entity not found")
        
    props = node.get("data", {})
    file_path = props.get("file")
    if not file_path:
        return ToolResult(success=False, tool_name=f"get_{entity_type}", data="", error="No file path associated with this entity")
        
    try:
        source_code = storage.get_file(repo_id, file_path)
        entity_name = props.get("name", entity_id.split('.')[-1])
        
        extracted_source = _extract_ast_node(source_code, entity_name, ast_type)
        if not extracted_source:
            extracted_source = "Could not parse source block exactly, here is the file path: " + file_path
            
        truncated = False
        if len(extracted_source) > MAX_FILE_CHARS:
            extracted_source = extracted_source[:MAX_FILE_CHARS]
            truncated = True
            
        return ToolResult(
            success=True, 
            tool_name=f"get_{entity_type}", 
            data={
                "name": entity_name, 
                "file": file_path, 
                "source": extracted_source,
                "metadata": props
            },
            truncated=truncated
        )
    except Exception as e:
        return ToolResult(success=False, tool_name=f"get_{entity_type}", data="", error=str(e))


@tool_registry.register(
    name="get_function",
    description="Retrieve the source code and metadata for a specific function.",
    input_model=GetFunctionInput
)
async def handle_get_function(input: GetFunctionInput, context: Dict[str, Any]) -> ToolResult:
    return await _get_entity_source(input.entity_id, context, "function", ast.FunctionDef)


@tool_registry.register(
    name="get_class",
    description="Retrieve the source code and metadata for a specific class.",
    input_model=GetClassInput
)
async def handle_get_class(input: GetClassInput, context: Dict[str, Any]) -> ToolResult:
    return await _get_entity_source(input.entity_id, context, "class", ast.ClassDef)


@tool_registry.register(
    name="get_graph_context",
    description="Retrieve bounded graph relationships (e.g. CALLS, IMPORTS) around an entity.",
    input_model=GetGraphContextInput
)
async def handle_get_graph_context(input: GetGraphContextInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    
    # We will use Cypher to allow relationship filtering safely, without exposing raw cypher.
    allowed_rels = ["CALLS", "IMPORTS", "CONTAINS", "INHERITS", "DEFINES"]
    
    if input.relationship_types:
        rels = [r for r in input.relationship_types if r in allowed_rels]
    else:
        rels = allowed_rels
        
    rel_match = "|".join(rels)
    
    query = f"""
    MATCH (n {{snapshot_id: $snapshot_id}})
    WHERE n.qualified_name = $entity_id OR elementId(n) = $entity_id
    OPTIONAL MATCH (n)-[r:{rel_match}]-(m {{snapshot_id: $snapshot_id}})
    RETURN labels(n)[0] as type, n.qualified_name as qname, type(r) as rel_type, r.resolution as resolution, labels(m)[0] as m_type, m.qualified_name as m_qname
    LIMIT {MAX_GRAPH_NODES}
    """
    
    try:
        async with neo4j_driver.session() as session:
            result = await session.run(query, snapshot_id=str(snap_id), entity_id=input.entity_id)
            records = await result.data()
            
            formatted = []
            for r in records:
                if r.get('rel_type'):
                    formatted.append({
                        "source": r['qname'],
                        "type": r['type'],
                        "relationship": r['rel_type'],
                        "resolution": r.get('resolution', 'exact'),
                        "target": r['m_qname'],
                        "target_type": r['m_type']
                    })
            return ToolResult(success=True, tool_name="get_graph_context", data=formatted)
    except Exception as e:
        return ToolResult(success=False, tool_name="get_graph_context", data="", error=str(e))


@tool_registry.register(
    name="get_callers",
    description="Find which functions or modules call this entity.",
    input_model=GetCallersInput
)
async def handle_get_callers(input: GetCallersInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    impact = ImpactService(repo_id, snap_id, max_depth=1)
    
    try:
        result = await impact.analyze(input.entity_id, direction="upstream")
        data = {
            "target": result.target_name,
            "direct_callers": [e.__dict__ for e in result.direct_callers],
            "unresolved_references": [e.__dict__ for e in result.unresolved_references]
        }
        return ToolResult(success=True, tool_name="get_callers", data=data)
    except Exception as e:
        return ToolResult(success=False, tool_name="get_callers", data="", error=str(e))


@tool_registry.register(
    name="get_callees",
    description="Find which functions or modules are called by this entity.",
    input_model=GetCalleesInput
)
async def handle_get_callees(input: GetCalleesInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    impact = ImpactService(repo_id, snap_id, max_depth=1)
    
    try:
        result = await impact.analyze(input.entity_id, direction="downstream")
        data = {
            "target": result.target_name,
            "direct_callees": [e.__dict__ for e in result.direct_callees],
            "unresolved_references": [e.__dict__ for e in result.unresolved_references]
        }
        return ToolResult(success=True, tool_name="get_callees", data=data)
    except Exception as e:
        return ToolResult(success=False, tool_name="get_callees", data="", error=str(e))


@tool_registry.register(
    name="get_impact",
    description="Run deep deterministic impact analysis to trace upstream and downstream effects.",
    input_model=GetImpactInput
)
async def handle_get_impact(input: GetImpactInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    impact = ImpactService(repo_id, snap_id, max_depth=input.depth)
    
    try:
        result = await impact.analyze(input.entity_id, direction=input.direction)
        data = {
            "target": result.target_name,
            "summary": result.summary.__dict__,
            "affected_files": result.affected_files,
            "direct_callers": [e.name for e in result.direct_callers],
            "direct_callees": [e.name for e in result.direct_callees],
            "unresolved_references": [e.name for e in result.unresolved_references]
        }
        return ToolResult(success=True, tool_name="get_impact", data=data, truncated=result.traversal.truncated)
    except Exception as e:
        return ToolResult(success=False, tool_name="get_impact", data="", error=str(e))


@tool_registry.register(
    name="get_metrics",
    description="Get deterministic complexity, coupling, and risk metrics for an entity.",
    input_model=GetMetricsInput
)
async def handle_get_metrics(input: GetMetricsInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    
    try:
        result = await db.execute(
            select(EntityMetric)
            .where(EntityMetric.snapshot_id == snap_id)
            .where(EntityMetric.entity_name == input.entity_id)
        )
        metrics = result.scalars().all()
        
        data = {}
        for m in metrics:
            data[m.metric_name] = {
                "value": m.metric_value,
                "source": m.metric_source
            }
        return ToolResult(success=True, tool_name="get_metrics", data=data)
    except Exception as e:
        return ToolResult(success=False, tool_name="get_metrics", data="", error=str(e))


@tool_registry.register(
    name="get_git_context",
    description="Get file churn, recent contributors, and commit history for a file.",
    input_model=GetGitContextInput
)
async def handle_get_git_context(input: GetGitContextInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    
    try:
        churn_result = await db.execute(
            select(GitFileChurn)
            .where(GitFileChurn.snapshot_id == snap_id)
            .where(GitFileChurn.file_path == input.file_path)
        )
        churn = churn_result.scalars().first()
        
        if not churn:
            return ToolResult(success=False, tool_name="get_git_context", data="", error="No git data found for file")
            
        data = {
            "file": churn.file_path,
            "commit_count": churn.commit_count,
            "churn": churn.churn,
            "insertions": churn.total_insertions,
            "deletions": churn.total_deletions,
            "last_changed_at": str(churn.last_changed_at) if churn.last_changed_at else None
        }
        return ToolResult(success=True, tool_name="get_git_context", data=data)
    except Exception as e:
        return ToolResult(success=False, tool_name="get_git_context", data="", error=str(e))


@tool_registry.register(
    name="get_hotspots",
    description="Find files with HIGH or CRITICAL risk scores across the repository.",
    input_model=GetHotspotsInput
)
async def handle_get_hotspots(input: GetHotspotsInput, context: Dict[str, Any]) -> ToolResult:
    db, repo_id, snap_id = _get_context_vars(context)
    
    try:
        result = await db.execute(
            select(EntityMetric)
            .where(EntityMetric.snapshot_id == str(snap_id))
            .where(EntityMetric.metric_source == "archon_heuristic_v1")
            .where(EntityMetric.metric_name == "risk_score")
            .where(EntityMetric.metric_value >= 0.60)
            .order_by(desc(EntityMetric.metric_value))
            .limit(input.limit)
        )
        scores = result.scalars().all()
        
        data = []
        for s in scores:
            data.append({
                "file": s.entity_name,
                "risk_score": s.metric_value,
                "risk_label": classify_risk(s.metric_value)
            })
        return ToolResult(success=True, tool_name="get_hotspots", data=data)
    except Exception as e:
        return ToolResult(success=False, tool_name="get_hotspots", data="", error=str(e))


@tool_registry.register(name="compare_snapshots", description="Compare architectural evolution between two snapshots deterministically.", input_model=CompareSnapshotsInput)
async def compare_snapshots_handler(input_data: CompareSnapshotsInput, **context) -> ToolResult:
    repository_id = context.get("repository_id")
    if not repository_id:
        return ToolResult(success=False, error="repository_id context missing")
    
    db: AsyncSession = context.get("db")
    service = EvolutionService(db)
    
    try:
        comp = await service.compare_snapshots(
            repository_id, 
            uuid.UUID(input_data.previous_snapshot_id), 
            uuid.UUID(input_data.current_snapshot_id)
        )
        return ToolResult(success=True, data=comp.model_dump())
    except Exception as e:
        logger.error("compare_snapshots_error", error=str(e))
        return ToolResult(success=False, error=str(e))

@tool_registry.register(name="get_evolution_timeline", description="Get chronological list of snapshots and their top-level metrics.", input_model=GetEvolutionTimelineInput)
async def get_evolution_timeline_handler(input_data: GetEvolutionTimelineInput, **context) -> ToolResult:
    repository_id = context.get("repository_id")
    if not repository_id:
        return ToolResult(success=False, error="repository_id context missing")
    
    db: AsyncSession = context.get("db")
    service = EvolutionService(db)
    
    try:
        timeline = await service.get_timeline(repository_id)
        return ToolResult(success=True, data=[t.model_dump() for t in timeline])
    except Exception as e:
        logger.error("get_timeline_error", error=str(e))
        return ToolResult(success=False, error=str(e))

@tool_registry.register(name="get_drift_findings", description="Get Architecture Drift heuristic findings between two snapshots.", input_model=GetDriftFindingsInput)
async def get_drift_findings_handler(input_data: GetDriftFindingsInput, **context) -> ToolResult:
    repository_id = context.get("repository_id")
    if not repository_id:
        return ToolResult(success=False, error="repository_id context missing")
    
    db: AsyncSession = context.get("db")
    service = EvolutionService(db)
    
    try:
        comp = await service.compare_snapshots(
            repository_id, 
            uuid.UUID(input_data.previous_snapshot_id), 
            uuid.UUID(input_data.current_snapshot_id)
        )
        return ToolResult(success=True, data=[d.model_dump() for d in comp.drift_findings])
    except Exception as e:
        logger.error("get_drift_findings_error", error=str(e))
        return ToolResult(success=False, error=str(e))

@tool_registry.register(name="get_metric_trend", description="Get a specific entity's metric evolution over all snapshots.", input_model=GetMetricTrendInput)
async def get_metric_trend_handler(input_data: GetMetricTrendInput, **context) -> ToolResult:
    repository_id = context.get("repository_id")
    if not repository_id:
        return ToolResult(success=False, error="repository_id context missing")
    
    db: AsyncSession = context.get("db")
    service = EvolutionService(db)
    
    try:
        timeline = await service.get_timeline(repository_id)
        
        # Now fetch the entity metric for each snapshot in the timeline
        trends = []
        for snap in timeline:
            res = await db.execute(
                select(EntityMetric).where(
                    and_(
                        EntityMetric.snapshot_id == snap.snapshot_id,
                        EntityMetric.entity_name == input_data.entity_name
                    )
                )
            )
            metrics = {m.metric_name: m.metric_value for m in res.scalars().all()}
            if metrics:
                trends.append({
                    "snapshot_id": str(snap.snapshot_id),
                    "analyzed_at": str(snap.analyzed_at),
                    "metrics": metrics
                })
                
        return ToolResult(success=True, data=trends)
    except Exception as e:
        logger.error("get_metric_trend_error", error=str(e))
        return ToolResult(success=False, error=str(e))
