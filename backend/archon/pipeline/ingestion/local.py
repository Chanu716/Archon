import os
import shutil
from pathlib import Path
import uuid
import structlog
from archon.pipeline.ingestion.base import IngestionResult
from archon.pipeline.ingestion.scanner import scan_directory

logger = structlog.get_logger(__name__)

def import_local_repo(source_path: str, target_path: Path, repository_id: uuid.UUID) -> IngestionResult:
    """Copies a local directory to the target path and scans it."""
    source_dir = Path(source_path).resolve()
    
    if not source_dir.exists() or not source_dir.is_dir():
        logger.error("local_repo_not_found", source=str(source_dir))
        raise FileNotFoundError(f"Local repository path not found or not a directory: {source_path}")

    logger.info("importing_local_repo", source=str(source_dir), target=str(target_path))
    
    if target_path.exists():
        logger.info("removing_existing_dir", target=str(target_path))
        shutil.rmtree(target_path, ignore_errors=True)
        
    target_path.mkdir(parents=True, exist_ok=True)
    
    # We will use shutil.copytree but ignore common heavy dirs like .git to speed up MVP.
    # In a full version, we might want .git to extract commits, but since we copy, we 
    # could also extract commit hash right from the source.
    try:
        shutil.copytree(source_dir, target_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
            "__pycache__", "node_modules", "dist", "build", "target", "bin", "obj", "out",
            ".venv", "venv", ".idea", ".vscode", ".git", ".turbo", ".next", ".nuxt", "vendor", ".gradle", ".m2"
        ))
        logger.info("local_copy_success")
    except Exception as e:
        logger.error("local_copy_failed", error=str(e))
        raise Exception(f"Failed to copy local repository: {e}")
        
    # Attempt to get local commit hash if .git exists in source
    commit_sha = None
    try:
        import git
        repo = git.Repo(source_dir)
        commit_sha = repo.head.commit.hexsha
    except Exception:
        commit_sha = "unknown-local-commit"
        
    files = scan_directory(target_path)
    
    return IngestionResult(
        repository_id=repository_id,
        managed_path=target_path,
        commit_sha=commit_sha,
        files=files
    )
