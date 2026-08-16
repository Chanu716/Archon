import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any

from archon.api.deps import get_db
from archon.models.repository import Repository, AnalysisSnapshot
from archon.models.metrics import EntityMetric

router = APIRouter()

@router.get("/{repository_id}/health")
async def get_repository_health(repository_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Returns repository-wide health metrics based on the latest snapshot."""
    # Find latest snapshot
    result = await db.execute(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.repository_id == repository_id)
        .where(AnalysisSnapshot.is_latest == True)
        .order_by(AnalysisSnapshot.analyzed_at.desc())
    )
    snapshot = result.scalars().first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No analysis snapshot found for this repository")
        
    # Get all metrics for this snapshot
    metrics_result = await db.execute(
        select(EntityMetric)
        .where(EntityMetric.snapshot_id == snapshot.id)
    )
    all_metrics = metrics_result.scalars().all()
    
    # Calculate aggregates
    total_functions = len(set(m.entity_name for m in all_metrics if m.entity_type == "Function"))
    total_classes = len(set(m.entity_name for m in all_metrics if m.entity_type == "Class"))
    total_modules = len(set(m.entity_name for m in all_metrics if m.entity_type == "Module"))
    
    complexities = [m.metric_value for m in all_metrics if m.metric_name == "cyclomatic_complexity"]
    avg_complexity = sum(complexities) / len(complexities) if complexities else 0
    max_complexity = max(complexities) if complexities else 0
    
    cycles = [m.metric_value for m in all_metrics if m.metric_name == "circular_dependencies"]
    total_cycles = sum(cycles)
    
    high_complexity_count = len([c for c in complexities if c > 10]) # Arbitrary threshold for MVP
    
    couplings = [m.metric_value for m in all_metrics if m.metric_name == "outgoing_coupling"]
    high_coupling_count = len([c for c in couplings if c > 5]) # Arbitrary threshold for MVP
    
    return {
        "repository_id": repository_id,
        "snapshot_id": snapshot.id,
        "commit_sha": snapshot.commit_sha,
        "health": {
            "total_modules": total_modules,
            "total_classes": total_classes,
            "total_functions": total_functions,
            "average_complexity": round(avg_complexity, 2),
            "maximum_complexity": max_complexity,
            "circular_dependencies": total_cycles,
            "high_complexity_functions": high_complexity_count,
            "high_coupling_modules": high_coupling_count
        }
    }

@router.get("/{repository_id}/metrics/{entity_type}/{entity_name:path}")
async def get_entity_metrics(repository_id: uuid.UUID, entity_type: str, entity_name: str, db: AsyncSession = Depends(get_db)):
    """Returns specific metrics for a given entity in the latest snapshot."""
    result = await db.execute(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.repository_id == repository_id)
        .where(AnalysisSnapshot.is_latest == True)
        .order_by(AnalysisSnapshot.analyzed_at.desc())
    )
    snapshot = result.scalars().first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No analysis snapshot found")
        
    metrics_result = await db.execute(
        select(EntityMetric)
        .where(EntityMetric.snapshot_id == snapshot.id)
        .where(EntityMetric.entity_type.ilike(entity_type))
        .where(EntityMetric.entity_name == entity_name)
    )
    metrics = metrics_result.scalars().all()
    
    if not metrics:
        raise HTTPException(status_code=404, detail="Entity metrics not found")
        
    formatted = {m.metric_name: m.metric_value for m in metrics}
    # Separate sources for UI
    sources = {m.metric_name: m.metric_source for m in metrics}
    
    return {
        "entity_type": entity_type,
        "entity_name": entity_name,
        "metrics": formatted,
        "sources": sources
    }
