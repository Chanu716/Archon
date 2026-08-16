import os
from pathlib import Path
import uuid
import structlog
from archon.config import settings
from archon.utils.exceptions import PathTraversalError

logger = structlog.get_logger(__name__)

class RepositoryStorageService:
    def __init__(self, base_path: str = settings.REPOS_BASE_PATH):
        self.base_path = Path(base_path).resolve()
        
    def get_repository_path(self, repository_id: uuid.UUID) -> Path:
        """Returns the root path for a repository. Always within REPOS_BASE_PATH."""
        return self.base_path / str(repository_id)
        
    def resolve_safe_path(self, repository_id: uuid.UUID, relative_path: str) -> Path:
        """
        Resolves and validates a path. Uses Path.resolve() then checks
        the result is still inside the repository root.
        """
        repo_root = self.get_repository_path(repository_id)
        
        # Don't allow absolute paths to be passed as relative_path
        if Path(relative_path).is_absolute():
            logger.warning("path_traversal_attempt_absolute", repo_id=str(repository_id), path=relative_path)
            raise PathTraversalError("Absolute paths are not allowed.")
            
        target_path = (repo_root / relative_path).resolve()
        
        try:
            target_path.relative_to(repo_root)
        except ValueError:
            logger.warning("path_traversal_attempt_escape", repo_id=str(repository_id), path=relative_path)
            raise PathTraversalError("Attempted to access path outside repository root.")
            
        return target_path

    def get_file(self, repository_id: uuid.UUID, relative_path: str) -> str:
        """
        Safely reads a file from within a repository.
        Raises PathTraversalError if relative_path escapes the repository root.
        Never accepts absolute paths from user input.
        """
        target_path = self.resolve_safe_path(repository_id, relative_path)
        
        if not target_path.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
            
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
