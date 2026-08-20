import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from archon.api.deps import get_db
from archon.services.investigation_service import InvestigationService
from archon.models.investigation import (
    InvestigationBaseResponse, GitContext, ImpactContext, 
    EvolutionContext, SemanticContext
)

router = APIRouter()

@router.get("/{repository_id}/investigation/{entity_id}", response_model=InvestigationBaseResponse)
async def get_investigation_base(
    repository_id: uuid.UUID,
    entity_id: str,
    snapshot_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the deterministic base context (overview, code, health, graph)
    for a given entity, enforcing snapshot isolation.
    """
    service = InvestigationService(db, repository_id)
    try:
        return await service.get_base_investigation(entity_id, snapshot_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{repository_id}/investigation/{entity_id}/git", response_model=Optional[GitContext])
async def get_investigation_git(
    repository_id: uuid.UUID,
    entity_id: str,
    snapshot_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Lazy-loads the Git intelligence section."""
    service = InvestigationService(db, repository_id)
    try:
        context = await service.get_context(entity_id, snapshot_id)
        return await service.get_git(context)
    except Exception:
        return GitContext(commit_count=0, churn=0.0, recent_commits=[])


@router.get("/{repository_id}/investigation/{entity_id}/impact", response_model=Optional[ImpactContext])
async def get_investigation_impact(
    repository_id: uuid.UUID,
    entity_id: str,
    snapshot_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Lazy-loads the Impact intelligence section."""
    service = InvestigationService(db, repository_id)
    try:
        context = await service.get_context(entity_id, snapshot_id)
        return await service.get_impact(context)
    except Exception:
        return ImpactContext(
            direct_callers=0, indirect_callers=0,
            direct_callees=0, indirect_callees=0,
            affected_entities=0, graph={"nodes": [], "edges": []}
        )


@router.get("/{repository_id}/investigation/{entity_id}/evolution", response_model=Optional[EvolutionContext])
async def get_investigation_evolution(
    repository_id: uuid.UUID,
    entity_id: str,
    snapshot_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Lazy-loads the Evolution timeline and drift findings."""
    service = InvestigationService(db, repository_id)
    try:
        context = await service.get_context(entity_id, snapshot_id)
        return await service.get_evolution(context)
    except Exception:
        return EvolutionContext(lifecycle=None, relationship_changes=[], drift_findings=[])


@router.get("/{repository_id}/investigation/{entity_id}/semantic", response_model=Optional[SemanticContext])
async def get_investigation_semantic(
    repository_id: uuid.UUID,
    entity_id: str,
    snapshot_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Lazy-loads Semantic relations using pgvector."""
    service = InvestigationService(db, repository_id)
    try:
        context = await service.get_context(entity_id, snapshot_id)
        return await service.get_semantic(context)
    except Exception:
        return SemanticContext(related_entities=[])
