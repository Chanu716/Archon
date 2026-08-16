import pytest
from pathlib import Path
import uuid
from archon.services.storage_service import RepositoryStorageService
from archon.utils.exceptions import PathTraversalError

def test_safe_path_resolution(tmp_path):
    repo_id = uuid.uuid4()
    service = RepositoryStorageService(base_path=str(tmp_path))
    
    # Ensure it constructs correctly
    repo_path = service.get_repository_path(repo_id)
    assert repo_path == tmp_path / str(repo_id)
    
    # Ensure safe sub-paths work
    safe_path = service.resolve_safe_path(repo_id, "main.py")
    assert safe_path == tmp_path / str(repo_id) / "main.py"
    
def test_path_traversal_prevention(tmp_path):
    repo_id = uuid.uuid4()
    service = RepositoryStorageService(base_path=str(tmp_path))
    
    with pytest.raises(PathTraversalError):
        service.resolve_safe_path(repo_id, "../outside.py")
        
    with pytest.raises(PathTraversalError):
        service.resolve_safe_path(repo_id, "/etc/passwd")
