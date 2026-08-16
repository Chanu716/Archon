"""
Git Intelligence Analyzer

Extracts deterministic Git history metrics from a local .git repository.

Security model:
  - Uses GitPython's object API only — no shell-out to user scripts
  - Never executes repository-controlled code
  - Read-only access to .git history

Snapshot cutoff:
  - If snapshot.commit_sha is set, history is extracted only up to that commit
  - This guarantees that a snapshot's Git data does not include future commits

History window (applied in order of whichever is hit first):
  - GIT_MAX_COMMITS (default 1000)
  - GIT_SINCE_DAYS (default 365 days)

Churn definition:
  churn(file) = total_insertions + total_deletions across all commits in window
  This is the definition used by Archon Risk Heuristic v1.

Normalization:
  normalized_churn = churn / max_churn   [max-normalization]
  If max_churn == 0: normalized_churn = 0.0  (no division by zero)
"""
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import structlog

from archon.config import settings
from archon.db.session import async_session_factory
from archon.models.git import GitCommit, GitFileChange, GitFileChurn, GitContributor

logger = structlog.get_logger(__name__)


class GitAnalyzer:
    def __init__(
        self,
        repository_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        managed_path: str,
        snapshot_commit_sha: Optional[str] = None,
    ):
        self.repository_id = repository_id
        self.snapshot_id = snapshot_id
        self.managed_path = managed_path
        self.snapshot_commit_sha = snapshot_commit_sha

    async def run(self) -> bool:
        """
        Run the full Git analysis pipeline.
        Returns True if Git data was available, False if not a Git repository.
        """
        try:
            import git as gitpython  # GitPython
        except ImportError:
            logger.error("gitpython_not_installed")
            return False

        try:
            repo = gitpython.Repo(self.managed_path, search_parent_directories=False)
        except gitpython.InvalidGitRepositoryError:
            logger.warning("not_a_git_repository", path=self.managed_path)
            return False
        except gitpython.NoSuchPathError:
            logger.warning("git_path_not_found", path=self.managed_path)
            return False

        logger.info("git_analysis_starting", snapshot_id=str(self.snapshot_id))

        commits_data, file_changes_data = self._extract_history(repo)
        churn_data = self._aggregate_churn(file_changes_data)
        contributors_data = self._aggregate_contributors(commits_data, file_changes_data)

        await self._persist(commits_data, file_changes_data, churn_data, contributors_data)

        logger.info(
            "git_analysis_complete",
            commits=len(commits_data),
            files=len(churn_data),
            contributors=len(contributors_data),
        )
        return True

    def _extract_history(
        self, repo
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Extracts commits and file changes from Git history.

        Applies:
          1. Snapshot cutoff: starts from snapshot_commit_sha if set
          2. Date window: GIT_SINCE_DAYS
          3. Count window: GIT_MAX_COMMITS
        """
        since = datetime.now(timezone.utc) - timedelta(days=settings.GIT_SINCE_DAYS)
        max_commits = settings.GIT_MAX_COMMITS

        # Determine starting ref
        start_ref = self.snapshot_commit_sha or "HEAD"

        try:
            commits_iter = repo.iter_commits(
                rev=start_ref,
                max_count=max_commits,
                after=since.isoformat(),
            )
        except Exception as e:
            logger.warning("git_iter_commits_failed", error=str(e))
            return [], []

        commits_data: List[Dict] = []
        file_changes_data: List[Dict] = []

        for commit in commits_iter:
            try:
                author_name = commit.author.name or "Unknown"
                author_email = commit.author.email or "unknown@unknown"
                committed_at = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)

                commits_data.append({
                    "commit_sha": commit.hexsha,
                    "author_name": author_name,
                    "author_email": author_email,
                    "committed_at": committed_at,
                    "message": (commit.message or "")[:1000],
                })

                # Determine if the parent commit is accessible (handle shallow clones)
                has_valid_parent = True
                if commit.parents:
                    parent_sha = commit.parents[0].hexsha
                    try:
                        # GitPython lazily evaluates objects, so we must force a read to verify existence
                        repo.git.rev_parse("--verify", f"{parent_sha}^{{commit}}")
                    except Exception:
                        has_valid_parent = False
                
                if not has_valid_parent:
                    logger.debug("git_commit_missing_parent", sha=commit.hexsha, msg="Skipping diff due to shallow boundary")
                    continue
                
                # Extract file-level stats
                # GitPython's stats give us insertions/deletions per file
                for file_path, stats in commit.stats.files.items():
                    # Determine change type
                    change_type = self._infer_change_type(commit, file_path)
                    file_changes_data.append({
                        "commit_sha": commit.hexsha,
                        "file_path": self._normalize_path(file_path),
                        "change_type": change_type,
                        "insertions": stats.get("insertions", 0),
                        "deletions": stats.get("deletions", 0),
                    })
            except Exception as e:
                logger.debug("git_commit_parse_error", sha=commit.hexsha[:8], error=str(e))
                continue

        return commits_data, file_changes_data

    def _infer_change_type(self, commit, file_path: str) -> str:
        """
        Infer the change type for a file in a commit.
        GitPython's stats don't directly expose A/M/D/R, so we inspect diff.
        Falls back to 'M' if detection fails (safe default for existing files).
        """
        try:
            if commit.parents:
                parent = commit.parents[0]
                diffs = parent.diff(commit)
                for diff in diffs:
                    diff_path = diff.b_path or diff.a_path
                    if diff_path == file_path:
                        return diff.change_type  # A/M/D/R from GitPython
            else:
                # Initial commit — everything is added
                return "A"
        except Exception:
            pass
        return "M"

    def _normalize_path(self, path: str) -> str:
        """Normalize path separators to forward slashes."""
        return path.replace("\\", "/")

    def _aggregate_churn(self, file_changes: List[Dict]) -> Dict[str, Dict]:
        """
        Aggregates per-file churn across all commits in the history window.

        churn(file) = total_insertions + total_deletions

        Then applies max-normalization:
          normalized_churn = churn / max_churn
          If max_churn == 0: normalized_churn = 0.0
        """
        file_stats: Dict[str, Dict] = defaultdict(lambda: {
            "commit_shas": set(),
            "total_insertions": 0,
            "total_deletions": 0,
            "last_changed_at": None,
            "first_changed_at": None,
        })

        # We need timestamps — build a commit_sha → timestamp map
        sha_to_time: Dict[str, datetime] = {}

        for fc in file_changes:
            path = fc["file_path"]
            sha = fc["commit_sha"]
            file_stats[path]["commit_shas"].add(sha)
            file_stats[path]["total_insertions"] += fc["insertions"]
            file_stats[path]["total_deletions"] += fc["deletions"]

        # Calculate churn
        churn_results: Dict[str, Dict] = {}
        max_churn = 0
        for path, stats in file_stats.items():
            churn = stats["total_insertions"] + stats["total_deletions"]
            max_churn = max(max_churn, churn)
            churn_results[path] = {
                "commit_count": len(stats["commit_shas"]),
                "total_insertions": stats["total_insertions"],
                "total_deletions": stats["total_deletions"],
                "churn": churn,
            }

        # Apply max-normalization
        for path, data in churn_results.items():
            if max_churn > 0:
                data["normalized_churn"] = data["churn"] / max_churn
            else:
                data["normalized_churn"] = 0.0

        return churn_results

    def _aggregate_contributors(
        self,
        commits: List[Dict],
        file_changes: List[Dict],
    ) -> List[Dict]:
        """Aggregates per-contributor activity across the history window."""
        contributor_stats: Dict[str, Dict] = defaultdict(lambda: {
            "author_name": "",
            "commit_shas": set(),
            "files_touched": set(),
            "total_insertions": 0,
            "total_deletions": 0,
            "commit_times": [],
        })

        # Build commit → author map
        sha_to_author: Dict[str, Tuple[str, str]] = {
            c["commit_sha"]: (c["author_name"], c["author_email"])
            for c in commits
        }
        sha_to_time: Dict[str, datetime] = {
            c["commit_sha"]: c["committed_at"] for c in commits
        }

        for commit in commits:
            email = commit["author_email"]
            contributor_stats[email]["author_name"] = commit["author_name"]
            contributor_stats[email]["commit_shas"].add(commit["commit_sha"])
            contributor_stats[email]["commit_times"].append(commit["committed_at"])

        for fc in file_changes:
            sha = fc["commit_sha"]
            if sha in sha_to_author:
                _, email = sha_to_author[sha]
                contributor_stats[email]["files_touched"].add(fc["file_path"])
                contributor_stats[email]["total_insertions"] += fc["insertions"]
                contributor_stats[email]["total_deletions"] += fc["deletions"]

        results = []
        for email, stats in contributor_stats.items():
            times = sorted(stats["commit_times"])
            results.append({
                "author_email": email,
                "author_name": stats["author_name"],
                "commit_count": len(stats["commit_shas"]),
                "files_touched": len(stats["files_touched"]),
                "total_insertions": stats["total_insertions"],
                "total_deletions": stats["total_deletions"],
                "first_commit_at": times[0] if times else None,
                "last_commit_at": times[-1] if times else None,
            })

        return results

    async def _persist(
        self,
        commits: List[Dict],
        file_changes: List[Dict],
        churn: Dict[str, Dict],
        contributors: List[Dict],
    ):
        """Persists all Git intelligence data to PostgreSQL in a single session."""
        async with async_session_factory() as db:
            # Commits
            for c in commits:
                db.add(GitCommit(
                    repository_id=self.repository_id,
                    snapshot_id=self.snapshot_id,
                    **c,
                ))

            # File changes (batch insert for performance)
            for fc in file_changes:
                db.add(GitFileChange(snapshot_id=self.snapshot_id, **fc))

            # Churn aggregates
            for file_path, data in churn.items():
                db.add(GitFileChurn(
                    snapshot_id=self.snapshot_id,
                    file_path=file_path,
                    **data,
                ))

            # Contributors
            for contrib in contributors:
                db.add(GitContributor(snapshot_id=self.snapshot_id, **contrib))

            await db.commit()
