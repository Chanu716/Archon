import uuid
from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from archon.api.deps import get_db
from archon.services.evolution_service import EvolutionService
from archon.models.evolution import SnapshotComparison, TimelineNode

router = APIRouter()

@router.get("/repositories/{repository_id}/evolution/timeline", response_model=List[TimelineNode])
async def get_evolution_timeline(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    service = EvolutionService(db)
    return await service.get_timeline(repository_id)

@router.get("/repositories/{repository_id}/evolution/compare", response_model=SnapshotComparison)
async def compare_snapshots(
    repository_id: uuid.UUID,
    previous_snapshot_id: uuid.UUID = Query(...),
    current_snapshot_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db)
):
    service = EvolutionService(db)
    try:
        return await service.compare_snapshots(repository_id, previous_snapshot_id, current_snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
