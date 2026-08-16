import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from archon.api.deps import get_db
from archon.models.repository import AnalysisSnapshot
from archon.services.graph_service import GraphService

router = APIRouter()


async def _resolve_snapshot(repository_id: uuid.UUID, db: AsyncSession) -> AnalysisSnapshot:
    result = await db.execute(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.repository_id == repository_id)
        .where(AnalysisSnapshot.is_latest == True)
        .order_by(AnalysisSnapshot.analyzed_at.desc())
    )
    snapshot = result.scalars().first()
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="No analysis snapshot found for this repository. Run analysis first."
        )
    return snapshot


@router.get("/repositories/{repo_id}/graph/overview")
async def get_graph_overview(repo_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Returns the top-level bounded graph view."""
    snapshot = await _resolve_snapshot(repo_id, db)
    service = GraphService(repository_id=repo_id, snapshot_id=snapshot.id)
    return await service.get_overview()


@router.get("/repositories/{repo_id}/graph/search")
async def search_graph_nodes(repo_id: uuid.UUID, q: str = "", db: AsyncSession = Depends(get_db)):
    """Searches graph nodes by name."""
    snapshot = await _resolve_snapshot(repo_id, db)
    service = GraphService(repository_id=repo_id, snapshot_id=snapshot.id)
    return await service.search_nodes(q)


@router.get("/repositories/{repo_id}/graph/nodes/{node_id}")
async def get_node_details(repo_id: uuid.UUID, node_id: str, db: AsyncSession = Depends(get_db)):
    """Gets details for a specific node."""
    snapshot = await _resolve_snapshot(repo_id, db)
    service = GraphService(repository_id=repo_id, snapshot_id=snapshot.id)
    return await service.get_node_details(node_id)


@router.get("/repositories/{repo_id}/graph/nodes/{node_id}/expand")
async def expand_node(repo_id: uuid.UUID, node_id: str, db: AsyncSession = Depends(get_db)):
    """Expands relationships 1 hop out from a specific node."""
    snapshot = await _resolve_snapshot(repo_id, db)
    service = GraphService(repository_id=repo_id, snapshot_id=snapshot.id)
    return await service.expand_node(node_id)
