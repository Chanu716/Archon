from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from archon.models.repository import Repository
from archon.models.repository import AnalysisSnapshot
import uuid
from typing import List, Dict

class RepositoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_repository(self, name: str, source_url: str) -> Repository:
        repo = Repository(
            name=name,
            source_type="github",
            source_url=source_url,
            managed_path="" # Set when first analyzed
        )
        self.db.add(repo)
        await self.db.commit()
        await self.db.refresh(repo)
        return repo

    async def get_repository(self, repo_id: uuid.UUID) -> Repository:
        stmt = select(Repository).where(Repository.id == repo_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_repositories(self) -> List[Dict]:
        """Returns repositories with has_snapshot populated from AnalysisSnapshot."""
        repos_stmt = select(Repository).order_by(Repository.created_at.desc())
        repos_result = await self.db.execute(repos_stmt)
        repos = list(repos_result.scalars().all())

        # Fetch the set of repository IDs that have at least one snapshot
        snap_stmt = select(AnalysisSnapshot.repository_id).distinct()
        snap_result = await self.db.execute(snap_stmt)
        snapped_repo_ids = {str(row[0]) for row in snap_result.all()}

        # Build response dicts with has_snapshot injected
        result_list = []
        for repo in repos:
            d = {
                "id": repo.id,
                "name": repo.name,
                "source_type": repo.source_type,
                "source_url": repo.source_url,
                "detected_languages": repo.detected_languages,
                "last_analyzed_at": repo.last_analyzed_at,
                "last_analyzed_commit": repo.last_analyzed_commit,
                "created_at": repo.created_at,
                "has_snapshot": str(repo.id) in snapped_repo_ids,
            }
            result_list.append(d)
        return result_list
