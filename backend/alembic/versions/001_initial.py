"""initial

Revision ID: 001_initial
Revises: 
Create Date: 2026-08-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. repositories table
    op.create_table('repositories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_url', sa.String(length=1024), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_repositories_id'), 'repositories', ['id'], unique=False)
    op.create_index(op.f('ix_repositories_source_url'), 'repositories', ['source_url'], unique=False)

    # 2. analysis_jobs table
    op.create_table('analysis_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('repository_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False),
        sa.Column('current_step', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_jobs_id'), 'analysis_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_analysis_jobs_repository_id'), 'analysis_jobs', ['repository_id'], unique=False)

    # 3. analysis_snapshots table
    op.create_table('analysis_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('repository_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('commit_sha', sa.String(length=40), nullable=True),
        sa.Column('archon_version', sa.String(length=50), nullable=False),
        sa.Column('parser_version', sa.String(length=50), nullable=False),
        sa.Column('is_latest', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['analysis_job_id'], ['analysis_jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_snapshots_id'), 'analysis_snapshots', ['id'], unique=False)
    op.create_index(op.f('ix_analysis_snapshots_repository_id'), 'analysis_snapshots', ['repository_id'], unique=False)
    op.create_index(op.f('ix_analysis_snapshots_is_latest'), 'analysis_snapshots', ['is_latest'], unique=False)

    # 4. entity_metrics table
    op.create_table('entity_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_name', sa.String(length=500), nullable=False),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('metric_source', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['snapshot_id'], ['analysis_snapshots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entity_metrics_id'), 'entity_metrics', ['id'], unique=False)
    op.create_index(op.f('ix_entity_metrics_snapshot_id'), 'entity_metrics', ['snapshot_id'], unique=False)
    op.create_index(op.f('ix_entity_metrics_metric_source'), 'entity_metrics', ['metric_source'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_entity_metrics_metric_source'), table_name='entity_metrics')
    op.drop_index(op.f('ix_entity_metrics_snapshot_id'), table_name='entity_metrics')
    op.drop_index(op.f('ix_entity_metrics_id'), table_name='entity_metrics')
    op.drop_table('entity_metrics')
    
    op.drop_index(op.f('ix_analysis_snapshots_is_latest'), table_name='analysis_snapshots')
    op.drop_index(op.f('ix_analysis_snapshots_repository_id'), table_name='analysis_snapshots')
    op.drop_index(op.f('ix_analysis_snapshots_id'), table_name='analysis_snapshots')
    op.drop_table('analysis_snapshots')
    
    op.drop_index(op.f('ix_analysis_jobs_repository_id'), table_name='analysis_jobs')
    op.drop_index(op.f('ix_analysis_jobs_id'), table_name='analysis_jobs')
    op.drop_table('analysis_jobs')
    
    op.drop_index(op.f('ix_repositories_source_url'), table_name='repositories')
    op.drop_index(op.f('ix_repositories_id'), table_name='repositories')
    op.drop_table('repositories')
