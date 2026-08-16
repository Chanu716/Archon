"""restore_indexes

Revision ID: d91e0b02032f
Revises: b6d874277cd9
Create Date: 2026-08-13 14:01:03.304613

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd91e0b02032f'
down_revision: Union[str, None] = 'b6d874277cd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Restore missing indexes
    op.create_index(op.f('ix_repositories_id'), 'repositories', ['id'], unique=False)
    op.create_index(op.f('ix_repositories_source_url'), 'repositories', ['source_url'], unique=False)
    
    op.create_index(op.f('ix_analysis_jobs_id'), 'analysis_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_analysis_jobs_repository_id'), 'analysis_jobs', ['repository_id'], unique=False)
    
    op.create_index(op.f('ix_analysis_snapshots_id'), 'analysis_snapshots', ['id'], unique=False)
    op.create_index(op.f('ix_analysis_snapshots_repository_id'), 'analysis_snapshots', ['repository_id'], unique=False)
    op.create_index(op.f('ix_analysis_snapshots_is_latest'), 'analysis_snapshots', ['is_latest'], unique=False)
    
    # Fix the foreign key on analysis_snapshots
    op.drop_constraint(op.f('fk_analysis_snapshots_analysis_job_id_analysis_jobs'), 'analysis_snapshots', type_='foreignkey')
    op.create_foreign_key(op.f('fk_analysis_snapshots_analysis_job_id_analysis_jobs'), 'analysis_snapshots', 'analysis_jobs', ['analysis_job_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_analysis_snapshots_analysis_job_id_analysis_jobs'), 'analysis_snapshots', type_='foreignkey')
    op.create_foreign_key(op.f('fk_analysis_snapshots_analysis_job_id_analysis_jobs'), 'analysis_snapshots', 'analysis_jobs', ['analysis_job_id'], ['id'])
    
    op.drop_index(op.f('ix_analysis_snapshots_is_latest'), table_name='analysis_snapshots')
    op.drop_index(op.f('ix_analysis_snapshots_repository_id'), table_name='analysis_snapshots')
    op.drop_index(op.f('ix_analysis_snapshots_id'), table_name='analysis_snapshots')
    
    op.drop_index(op.f('ix_analysis_jobs_repository_id'), table_name='analysis_jobs')
    op.drop_index(op.f('ix_analysis_jobs_id'), table_name='analysis_jobs')
    
    op.drop_index(op.f('ix_repositories_source_url'), table_name='repositories')
    op.drop_index(op.f('ix_repositories_id'), table_name='repositories')
