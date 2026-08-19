import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from archon.api.deps import get_db, get_execution_adapter
from archon.execution.background_tasks import BackgroundTasksAdapter
from archon.models.repository import Repository
from archon.models.analysis_job import AnalysisJob
from archon.schemas.analysis import JobResponse, AnalyzeRequest
from archon.services.job_service import JobService

router = APIRouter()


async def _run_analysis_pipeline(job_id: uuid.UUID, repo: Repository):
    """Background task runner — wires into the full analysis pipeline."""
    from archon.pipeline.orchestrator import run_analysis_pipeline
    from archon.db.session import async_session_factory
    from archon.services.job_service import JobService
    import structlog
    
    logger = structlog.get_logger(__name__)

    async def progress_callback(j_id: uuid.UUID, progress: float, stage: str):
        try:
            async with async_session_factory() as db:
                service = JobService(db)
                await service.update_progress(j_id, progress, stage)
        except Exception as e:
            logger.error("failed_to_update_progress", job_id=str(j_id), error=str(e))

    await run_analysis_pipeline(
        repository_id=repo.id,
        job_id=job_id,
        source_url=repo.managed_path or repo.source_url,  # managed_path has token for private repos
        source_type=repo.source_type,
        progress_callback=progress_callback
    )


@router.post("/repositories/{repo_id}/analyze", response_model=JobResponse, status_code=202)
async def trigger_analysis(
    repo_id: uuid.UUID,
    payload: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    adapter: BackgroundTasksAdapter = Depends(get_execution_adapter),
):
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalars().first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    job_service = JobService(db)
    job = await job_service.create_job(repo_id)

    await adapter.submit(job.id, _run_analysis_pipeline, repo)

    return job


@router.get("/analysis-jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

