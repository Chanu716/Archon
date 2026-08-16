import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from archon.api.deps import get_db
from archon.models.repository import AnalysisSnapshot
from archon.services.semantic_search import SemanticSearchService
from sqlalchemy import select

router = APIRouter()


@router.get("/repositories/{repository_id}/search")
async def semantic_search(
    repository_id: uuid.UUID,
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Performs semantic similarity search over the repository's code entities."""
    result = await db.execute(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.repository_id == repository_id)
        .where(AnalysisSnapshot.is_latest == True)
        .order_by(AnalysisSnapshot.analyzed_at.desc())
    )
    snapshot = result.scalars().first()
    if not snapshot:
        return []

    service = SemanticSearchService(db)
    results = await service.search(
        repository_id=repository_id,
        query=q,
        snapshot_id=snapshot.id,
        limit=limit,
    )
    return results
