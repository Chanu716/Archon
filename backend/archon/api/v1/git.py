import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from archon.api.deps import get_db
from archon.models.repository import Repository, AnalysisSnapshot
from archon.models.git import GitCommit, GitFileChurn, GitContributor
from archon.models.metrics import EntityMetric

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


@router.get("/repositories/{repository_id}/git/overview")
async def get_git_overview(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Returns high-level Git intelligence overview for a repository."""
    snapshot = await _resolve_snapshot(repository_id, db)
    
    # Commit count
    commits_result = await db.execute(
        select(func.count(GitCommit.id)).where(GitCommit.snapshot_id == snapshot.id)
    )
    total_commits = commits_result.scalar() or 0

    # Contributor count
    contrib_result = await db.execute(
        select(func.count(GitContributor.id)).where(GitContributor.snapshot_id == snapshot.id)
    )
    total_contributors = contrib_result.scalar() or 0
    
    if total_commits == 0:
        return {
            "git_available": False,
            "total_commits": 0,
            "total_contributors": 0
        }

    return {
        "git_available": True,
        "total_commits": total_commits,
        "total_contributors": total_contributors,
        "snapshot_commit_sha": snapshot.commit_sha
    }


@router.get("/repositories/{repository_id}/git/commits")
async def get_git_commits(
    repository_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Returns recent commits analyzed for this snapshot."""
    snapshot = await _resolve_snapshot(repository_id, db)

    result = await db.execute(
        select(GitCommit)
        .where(GitCommit.snapshot_id == snapshot.id)
        .order_by(desc(GitCommit.committed_at))
        .limit(limit)
    )
    commits = result.scalars().all()
    
    return [
        {
            "sha": c.commit_sha,
            "author_name": c.author_name,
            "author_email": c.author_email,
            "committed_at": c.committed_at,
            "message": c.message
        }
        for c in commits
    ]


@router.get("/repositories/{repository_id}/git/files")
async def get_git_files(
    repository_id: uuid.UUID,
    sort_by: str = Query("churn", pattern="^(churn|recent)$"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Returns file churn data."""
    snapshot = await _resolve_snapshot(repository_id, db)

    query = select(GitFileChurn).where(GitFileChurn.snapshot_id == snapshot.id)
    
    if sort_by == "churn":
        query = query.order_by(desc(GitFileChurn.churn))
    else:
        query = query.order_by(desc(GitFileChurn.last_changed_at))
        
    result = await db.execute(query.limit(limit))
    files = result.scalars().all()
    
    return [
        {
            "file_path": f.file_path,
            "commit_count": f.commit_count,
            "insertions": f.total_insertions,
            "deletions": f.total_deletions,
            "churn": f.churn,
            "normalized_churn": f.normalized_churn,
            "last_changed_at": f.last_changed_at,
        }
        for f in files
    ]


@router.get("/repositories/{repository_id}/git/contributors")
async def get_git_contributors(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Returns contributor statistics."""
    snapshot = await _resolve_snapshot(repository_id, db)

    result = await db.execute(
        select(GitContributor)
        .where(GitContributor.snapshot_id == snapshot.id)
        .order_by(desc(GitContributor.commit_count))
    )
    contributors = result.scalars().all()
    
    return [
        {
            "author_name": c.author_name,
            "author_email": c.author_email,
            "commit_count": c.commit_count,
            "files_touched": c.files_touched,
            "insertions": c.total_insertions,
            "deletions": c.total_deletions,
            "first_commit_at": c.first_commit_at,
            "last_commit_at": c.last_commit_at,
        }
        for c in contributors
    ]


@router.get("/repositories/{repository_id}/git/hotspots")
async def get_git_hotspots(
    repository_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns Archon Risk Heuristic v1 hotspots.
    Only files classified as CRITICAL, HIGH, or MODERATE are returned.
    """
    snapshot = await _resolve_snapshot(repository_id, db)

    # We stored risk_score and risk_label
    result = await db.execute(
        select(EntityMetric)
        .where(EntityMetric.snapshot_id == str(snapshot.id))
        .where(EntityMetric.metric_source == "archon_heuristic_v1")
        .where(EntityMetric.metric_name == "risk_score")
        .where(EntityMetric.metric_value >= 0.30) # Only Moderate and above
        .order_by(desc(EntityMetric.metric_value))
        .limit(limit)
    )
    scores = result.scalars().all()
    
    # We also need the label, so let's just map score to label dynamically
    # to avoid complex joins for the MVP.
    def classify(s):
        from archon.pipeline.analysis.risk_calculator import classify_risk
        return classify_risk(s)
        
    hotspots = []
    for score in scores:
        hotspots.append({
            "file_path": score.entity_name,
            "risk_score": score.metric_value,
            "risk_label": classify(score.metric_value)
        })
        
    return hotspots
