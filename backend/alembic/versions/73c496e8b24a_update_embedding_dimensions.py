"""update_embedding_dimensions

Revision ID: 73c496e8b24a
Revises: d91e0b02032f
Create Date: 2026-08-13 14:38:08.381444

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73c496e8b24a'
down_revision: Union[str, None] = 'd91e0b02032f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # We must truncate the table because you cannot cast vector(1536) to vector(768) directly.
    op.execute("TRUNCATE TABLE code_embeddings;")
    op.execute("ALTER TABLE code_embeddings ALTER COLUMN embedding TYPE vector(768);")


def downgrade() -> None:
    op.execute("TRUNCATE TABLE code_embeddings;")
    op.execute("ALTER TABLE code_embeddings ALTER COLUMN embedding TYPE vector(1536);")
