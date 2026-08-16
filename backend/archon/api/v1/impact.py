import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from archon.api.deps import get_db
from archon.models.repository import AnalysisSnapshot
from archon.services.impact_service import ImpactService

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


@router.get("/repositories/{repository_id}/impact/{entity_id:path}")
async def get_impact(
    repository_id: uuid.UUID,
    entity_id: str,
    direction: str = "both",
    depth: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """
    Runs deterministic impact analysis for the given entity.

    direction: 'upstream' | 'downstream' | 'both'
    depth:     max BFS hops (1–10, clamped internally)
    """
    if direction not in ("upstream", "downstream", "both"):
        raise HTTPException(status_code=400, detail="direction must be 'upstream', 'downstream', or 'both'")

    snapshot = await _resolve_snapshot(repository_id, db)

    service = ImpactService(
        repository_id=repository_id,
        snapshot_id=snapshot.id,
        max_depth=min(max(depth, 1), 10),
    )

    try:
        result = await service.analyze(entity_id, direction=direction)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Serialize dataclasses to dicts
    def entity_to_dict(e):
        return {
            "id": e.id,
            "type": e.type,
            "name": e.name,
            "qualified_name": e.qualified_name,
            "file": e.file,
            "distance": e.distance,
            "relationship": e.relationship,
            "resolution": e.resolution,
            "path": e.path,
        }

    return {
        "target_id": result.target_id,
        "target_name": result.target_name,
        "target_type": result.target_type,
        "snapshot_id": result.snapshot_id,
        "summary": {
            "direct_callers": result.summary.direct_callers,
            "indirect_callers": result.summary.indirect_callers,
            "direct_callees": result.summary.direct_callees,
            "indirect_callees": result.summary.indirect_callees,
            "affected_files": result.summary.affected_files,
            "affected_modules": result.summary.affected_modules,
            "affected_classes": result.summary.affected_classes,
            "unresolved_references": result.summary.unresolved_references,
        },
        "traversal": {
            "max_depth": result.traversal.max_depth,
            "max_nodes": result.traversal.max_nodes,
            "actual_depth_reached": result.traversal.actual_depth_reached,
            "nodes_visited": result.traversal.nodes_visited,
            "truncated": result.traversal.truncated,
        },
        "direct_callers": [entity_to_dict(e) for e in result.direct_callers],
        "indirect_callers": [entity_to_dict(e) for e in result.indirect_callers],
        "direct_callees": [entity_to_dict(e) for e in result.direct_callees],
        "indirect_callees": [entity_to_dict(e) for e in result.indirect_callees],
        "affected_files": result.affected_files,
        "affected_modules": result.affected_modules,
        "affected_classes": result.affected_classes,
        "unresolved_references": [entity_to_dict(e) for e in result.unresolved_references],
    }
