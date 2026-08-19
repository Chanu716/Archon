import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from archon.api.deps import get_db
from archon.models.repository import Repository
from archon.schemas.repository import RepositoryCreate, RepositoryResponse
from archon.services.repository_service import RepositoryService

router = APIRouter()


@router.get("/repositories", response_model=list[RepositoryResponse])
async def list_repositories(db: AsyncSession = Depends(get_db)):
    """List all repositories."""
    svc = RepositoryService(db)
    return await svc.list_repositories()


@router.post("/repositories", response_model=RepositoryResponse, status_code=201)
async def create_repository(
    payload: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create (register) a new repository."""
    svc = RepositoryService(db)
    source_url = str(payload.source_url)
    name = source_url.rstrip("/").split("/")[-1].removesuffix(".git")
    repo = await svc.create_repository(
        name=name,
        source_url=source_url,
        github_token=payload.github_token,
    )
    return repo



@router.get("/repositories/{repo_id}", response_model=RepositoryResponse)
async def get_repository(repo_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a single repository by ID."""
    svc = RepositoryService(db)
    repo = await svc.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo
