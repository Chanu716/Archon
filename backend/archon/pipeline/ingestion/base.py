from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path
import uuid

@dataclass
class IngestionResult:
    repository_id: uuid.UUID
    managed_path: Path
    commit_sha: Optional[str]
    files: List[Path]
