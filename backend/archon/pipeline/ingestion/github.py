import os
import shutil
from pathlib import Path
import uuid
import git
import structlog
from archon.pipeline.ingestion.base import IngestionResult
from archon.pipeline.ingestion.scanner import scan_directory

logger = structlog.get_logger(__name__)

def clone_github_repo(source_url: str, target_path: Path, repository_id: uuid.UUID) -> IngestionResult:
    """Clones a GitHub repository to the target path and scans it."""
    logger.info("cloning_repo", url=source_url, target=str(target_path))
    
    if target_path.exists():
        logger.info("removing_existing_dir", target=str(target_path))
        shutil.rmtree(target_path, ignore_errors=True)
        
    target_path.mkdir(parents=True, exist_ok=True)
    
    try:
        repo = git.Repo.clone_from(source_url, target_path)
        commit_sha = repo.head.commit.hexsha
        logger.info("clone_success", commit=commit_sha)
    except git.GitCommandError as e:
        logger.error("clone_failed", error=str(e))
        raise Exception(f"Failed to clone repository: {e}")
        
    files = scan_directory(target_path)
    
    return IngestionResult(
        repository_id=repository_id,
        managed_path=target_path,
        commit_sha=commit_sha,
        files=files
    )
