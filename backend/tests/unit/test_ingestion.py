import pytest
import uuid
from pathlib import Path
from archon.pipeline.ingestion.local import import_local_repo
from archon.services.storage_service import RepositoryStorageService
from archon.utils.exceptions import PathTraversalError

def test_local_repo_import(tmp_path):
    repo_id = uuid.uuid4()
    
    # Create fake source repo
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "main.py").write_text("print('hello')")
    
    # Create storage target
    storage_dir = tmp_path / "storage"
    service = RepositoryStorageService(base_path=str(storage_dir))
    target_path = service.get_repository_path(repo_id)
    
    result = import_local_repo(str(source_dir), target_path, repo_id)
    
    assert result.repository_id == repo_id
    assert result.managed_path == target_path
    assert len(result.files) == 1
    assert "main.py" in str(result.files[0])
    
    # Verify file copied securely
    assert (target_path / "main.py").exists()

def test_local_repo_missing(tmp_path):
    repo_id = uuid.uuid4()
    storage_dir = tmp_path / "storage"
    service = RepositoryStorageService(base_path=str(storage_dir))
    
    with pytest.raises(FileNotFoundError):
        import_local_repo(str(tmp_path / "missing"), service.get_repository_path(repo_id), repo_id)
