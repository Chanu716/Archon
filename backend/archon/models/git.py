"""
PostgreSQL models for Git Intelligence.

All Git data is associated with:
  repository_id → the repository being analyzed
  snapshot_id   → the AnalysisSnapshot whose commit_sha defines the cutoff

Git data NEVER contains commits beyond the snapshot's commit_sha.
This is essential for correct snapshot-to-snapshot comparison in future slices.
"""
from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, Float,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from archon.models.base import Base
import uuid


class GitCommit(Base):
    """
    A single Git commit within the analyzed history window.

    History window constraints:
      - max GIT_MAX_COMMITS commits (default 1000)
      - max GIT_SINCE_DAYS days back (default 365)
      - commits must not be newer than the snapshot's commit_sha
    """
    __tablename__ = "git_commits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    snapshot_id   = Column(UUID(as_uuid=True), ForeignKey("analysis_snapshots.id", ondelete="CASCADE"), nullable=False)

    commit_sha    = Column(String(40), nullable=False)
    author_name   = Column(String(255), nullable=False)
    author_email  = Column(String(255), nullable=False)
    committed_at  = Column(DateTime(timezone=True), nullable=False)
    message       = Column(String(1000), nullable=True)   # first 1000 chars only

    __table_args__ = (
        UniqueConstraint("snapshot_id", "commit_sha", name="uq_git_commit_snapshot_sha"),
        Index("ix_git_commits_snapshot_id", "snapshot_id"),
        Index("ix_git_commits_repository_id", "repository_id"),
    )


class GitFileChange(Base):
    """
    A single file-level change within a commit.

    change_type follows Git conventions:
      A = Added
      M = Modified
      D = Deleted
      R = Renamed (file_path is the new path)

    churn = insertions + deletions
    This is an explicit, documented definition — NOT lines of code.
    """
    __tablename__ = "git_file_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id   = Column(UUID(as_uuid=True), ForeignKey("analysis_snapshots.id", ondelete="CASCADE"), nullable=False)
    commit_sha    = Column(String(40), nullable=False)
    file_path     = Column(String(1000), nullable=False)
    change_type   = Column(String(1), nullable=False)   # A / M / D / R
    insertions    = Column(Integer, nullable=False, default=0)
    deletions     = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_git_file_changes_snapshot_id", "snapshot_id"),
        Index("ix_git_file_changes_file_path", "snapshot_id", "file_path"),
    )


class GitFileChurn(Base):
    """
    Pre-aggregated churn statistics per file, per snapshot.

    churn_definition: "total insertions + total deletions across the analysis window"
    This is the deterministic definition used by Archon Risk Heuristic v1.

    normalized_churn: churn / max_churn across all files in this snapshot.
    Normalization method: max-normalization (not min-max).
    Edge case: if max_churn == 0, normalized_churn = 0.
    """
    __tablename__ = "git_file_churn"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id      = Column(UUID(as_uuid=True), ForeignKey("analysis_snapshots.id", ondelete="CASCADE"), nullable=False)
    file_path        = Column(String(1000), nullable=False)
    commit_count     = Column(Integer, nullable=False, default=0)
    total_insertions = Column(Integer, nullable=False, default=0)
    total_deletions  = Column(Integer, nullable=False, default=0)
    churn            = Column(Integer, nullable=False, default=0)    # insertions + deletions
    normalized_churn = Column(Float, nullable=False, default=0.0)
    last_changed_at  = Column(DateTime(timezone=True), nullable=True)
    first_changed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("snapshot_id", "file_path", name="uq_git_file_churn_snapshot_path"),
        Index("ix_git_file_churn_snapshot_id", "snapshot_id"),
    )


class GitContributor(Base):
    """
    Per-contributor activity aggregated at the snapshot level.

    IMPORTANT: This records repository activity, not developer performance.
    Git activity is historical metadata, not a measure of code quality.
    """
    __tablename__ = "git_contributors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id    = Column(UUID(as_uuid=True), ForeignKey("analysis_snapshots.id", ondelete="CASCADE"), nullable=False)
    author_name    = Column(String(255), nullable=False)
    author_email   = Column(String(255), nullable=False)
    commit_count   = Column(Integer, nullable=False, default=0)
    files_touched  = Column(Integer, nullable=False, default=0)    # distinct files changed
    total_insertions = Column(Integer, nullable=False, default=0)
    total_deletions  = Column(Integer, nullable=False, default=0)
    first_commit_at  = Column(DateTime(timezone=True), nullable=True)
    last_commit_at   = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("snapshot_id", "author_email", name="uq_git_contributor_snapshot_email"),
        Index("ix_git_contributors_snapshot_id", "snapshot_id"),
    )
