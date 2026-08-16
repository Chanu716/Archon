import os
from pathlib import Path
from typing import List
import structlog

logger = structlog.get_logger(__name__)

IGNORE_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", 
    "node_modules", "dist", "build", ".idea", ".vscode"
}

def scan_directory(root_path: Path) -> List[Path]:
    """Scans a directory for supported files, ignoring standard exclude lists."""
    files = []
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Modify dirnames in-place to avoid traversing ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        
        current_dir = Path(dirpath)
        for filename in filenames:
            # MVP: Only python files
            if filename.endswith(".py"):
                files.append(current_dir / filename)
                
    logger.info("directory_scanned", count=len(files), root=str(root_path))
    return files
