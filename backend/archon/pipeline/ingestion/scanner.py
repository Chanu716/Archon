"""
Repository File Scanner (ML-1)

Scans a repository directory and returns the paths of files that have a
registered parser. The scanner consults the ParserRegistry to determine
which extensions are supported — it does NOT hardcode any language-specific
extensions.

This is the correct extension point: adding a new language parser
(e.g., TypeScript) automatically makes the scanner pick up .ts/.tsx files
with no changes required here.
"""

import os
from pathlib import Path
from typing import List, Tuple
import structlog

from archon.pipeline.parsers.registry import registry
from archon.pipeline.parsers.base import SkipRecord

logger = structlog.get_logger(__name__)

IGNORE_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__",
    "node_modules", "dist", "build", "target", "bin", "obj", "out",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache", "coverage", ".tox",
    ".turbo", ".next", ".nuxt", "vendor", ".gradle", ".m2", ".cargo"
}


def scan_directory(root_path: Path) -> List[Path]:
    """
    Scan a directory for files that have a registered parser.

    Files whose extension is not registered in the ParserRegistry are
    skipped and logged as SkipRecords. No hardcoded extension lists.

    Args:
        root_path: Absolute path to the repository root.

    Returns:
        List of Path objects for parseable files.
    """
    files: List[Path] = []
    skipped: List[SkipRecord] = []

    # Snapshot the supported extensions at scan time (deterministic, no mutation)
    supported = registry.supported_extensions()

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune ignored directories in-place to prevent traversal
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

        current_dir = Path(dirpath)
        for filename in filenames:
            ext = Path(filename).suffix
            if ext in supported:
                files.append(current_dir / filename)
            else:
                skipped.append(SkipRecord(
                    path=str(current_dir / filename),
                    extension=ext,
                    reason="unsupported_extension",
                ))

    logger.info(
        "directory_scanned",
        parseable_count=len(files),
        skipped_count=len(skipped),
        root=str(root_path),
        supported_extensions=sorted(supported),
    )

    if skipped:
        # Log at debug level; these are expected (images, configs, etc.)
        logger.debug(
            "files_skipped",
            count=len(skipped),
            sample_extensions=sorted({s.extension for s in skipped})[:10],
        )

    return files
