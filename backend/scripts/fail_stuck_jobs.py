import asyncio
import uuid
from sqlalchemy import update
from archon.db.session import async_session_factory
from archon.models.analysis_job import AnalysisJob
from archon.models.repository import Repository

async def fail_stuck_jobs():
    async with async_session_factory() as db:
        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.status == "queued")
            .values(status="failed", error_message="Job failed silently due to backend restart.")
        )
        await db.execute(stmt)
        
        stmt_running = (
            update(AnalysisJob)
            .where(AnalysisJob.status == "running")
            .values(status="failed", error_message="Job failed silently due to backend restart.")
        )
        await db.execute(stmt_running)
        
        await db.commit()
        print("Stuck jobs updated to failed.")

if __name__ == "__main__":
    asyncio.run(fail_stuck_jobs())
