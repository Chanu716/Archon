"""Add git intelligence tables

Revision ID: 002_git_tables
Revises: 001_initial
Create Date: 2026-08-12 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_git_tables'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # git_commits
    op.create_table('git_commits',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('repository_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id',   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('commit_sha',    sa.String(length=40),  nullable=False),
        sa.Column('author_name',   sa.String(length=255), nullable=False),
        sa.Column('author_email',  sa.String(length=255), nullable=False),
        sa.Column('committed_at',  sa.DateTime(timezone=True), nullable=False),
        sa.Column('message',       sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'],  ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['snapshot_id'],   ['analysis_snapshots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_id', 'commit_sha', name='uq_git_commit_snapshot_sha'),
    )
    op.create_index('ix_git_commits_snapshot_id',    'git_commits', ['snapshot_id'])
    op.create_index('ix_git_commits_repository_id',  'git_commits', ['repository_id'])

    # git_file_changes
    op.create_table('git_file_changes',
        sa.Column('id',          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('commit_sha',  sa.String(length=40),   nullable=False),
        sa.Column('file_path',   sa.String(length=1000), nullable=False),
        sa.Column('change_type', sa.String(length=1),    nullable=False),
        sa.Column('insertions',  sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deletions',   sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['snapshot_id'], ['analysis_snapshots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_git_file_changes_snapshot_id', 'git_file_changes', ['snapshot_id'])
    op.create_index('ix_git_file_changes_file_path',   'git_file_changes', ['snapshot_id', 'file_path'])

    # git_file_churn
    op.create_table('git_file_churn',
        sa.Column('id',               postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id',      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_path',        sa.String(length=1000), nullable=False),
        sa.Column('commit_count',     sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_insertions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_deletions',  sa.Integer(), nullable=False, server_default='0'),
        sa.Column('churn',            sa.Integer(), nullable=False, server_default='0'),
        sa.Column('normalized_churn', sa.Float(),   nullable=False, server_default='0'),
        sa.Column('last_changed_at',  sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['snapshot_id'], ['analysis_snapshots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_id', 'file_path', name='uq_git_file_churn_snapshot_path'),
    )
    op.create_index('ix_git_file_churn_snapshot_id', 'git_file_churn', ['snapshot_id'])

    # git_contributors
    op.create_table('git_contributors',
        sa.Column('id',                postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id',       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('author_name',       sa.String(length=255), nullable=False),
        sa.Column('author_email',      sa.String(length=255), nullable=False),
        sa.Column('commit_count',      sa.Integer(), nullable=False, server_default='0'),
        sa.Column('files_touched',     sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_insertions',  sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_deletions',   sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_commit_at',   sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_commit_at',    sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['snapshot_id'], ['analysis_snapshots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_id', 'author_email', name='uq_git_contributor_snapshot_email'),
    )
    op.create_index('ix_git_contributors_snapshot_id', 'git_contributors', ['snapshot_id'])


def downgrade() -> None:
    op.drop_index('ix_git_contributors_snapshot_id', 'git_contributors')
    op.drop_table('git_contributors')
    op.drop_index('ix_git_file_churn_snapshot_id', 'git_file_churn')
    op.drop_table('git_file_churn')
    op.drop_index('ix_git_file_changes_file_path',   'git_file_changes')
    op.drop_index('ix_git_file_changes_snapshot_id', 'git_file_changes')
    op.drop_table('git_file_changes')
    op.drop_index('ix_git_commits_repository_id', 'git_commits')
    op.drop_index('ix_git_commits_snapshot_id',   'git_commits')
    op.drop_table('git_commits')
