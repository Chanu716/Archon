"""Add semantic search embeddings table

Revision ID: 003_semantic_search
Revises: 002_git_tables
Create Date: 2026-08-12 16:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

revision: str = '003_semantic_search'
down_revision: Union[str, None] = '002_git_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ensure pgvector extension is enabled
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')

    # 2. Create the code_embeddings table
    op.create_table('code_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('repository_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_id', sa.String(length=1000), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('source_text', sa.String(), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(1536), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['snapshot_id'], ['analysis_snapshots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Create normal indexes for lookup
    op.create_index('ix_code_embeddings_snapshot_id', 'code_embeddings', ['snapshot_id'])
    op.create_index('ix_code_embeddings_repo_snapshot', 'code_embeddings', ['repository_id', 'snapshot_id'])


def downgrade() -> None:
    op.drop_index('ix_code_embeddings_repo_snapshot', table_name='code_embeddings')
    op.drop_index('ix_code_embeddings_snapshot_id', table_name='code_embeddings')
    op.drop_table('code_embeddings')
