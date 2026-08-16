from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from archon.models.analysis_job import AnalysisJob
from archon.models.repository import Repository
import uuid
import structlog
from datetime import datetime, timezone

logger = structlog.get_logger(__name__)

class JobService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, repository_id: uuid.UUID) -> AnalysisJob:
        job = AnalysisJob(
            repository_id=repository_id,
            status="queued",
            current_stage="queued",
            progress=0.0
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def update_progress(self, job_id: uuid.UUID, progress: float, stage: str):
        stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        
        if not job:
            logger.error("job_not_found_for_progress_update", job_id=str(job_id))
            return
            
        job.progress = progress
        job.current_stage = stage
        
        if progress == 0.0:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            
        if progress == 100.0:
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            repo_stmt = select(Repository).where(Repository.id == job.repository_id)
            repo_result = await self.db.execute(repo_stmt)
            repo = repo_result.scalar_one_or_none()
            if repo:
                repo.last_analyzed_at = job.completed_at
            
        if progress < 0.0:
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            
        await self.db.commit()
