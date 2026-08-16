"""
PostgreSQL models for Semantic Code Search (Embeddings).

Requires the pgvector extension.
All embeddings are bound to a specific snapshot to ensure search results
are strictly isolated to the exact state of the repository at that time.
"""
import uuid
from sqlalchemy import Column, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from archon.models.base import Base
from archon.config import settings

class CodeEmbedding(Base):
    __tablename__ = "code_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("analysis_snapshots.id", ondelete="CASCADE"), nullable=False)
    
    # Identifier for the semantic unit (e.g., function qualified name)
    entity_id = Column(String(1000), nullable=False)
    
    # Entity Type: "Function", "Class", "Module"
    entity_type = Column(String(50), nullable=False)
    
    # File path for navigation
    file_path = Column(String(1000), nullable=False)
    
    # The actual semantic unit text that was embedded (source + context)
    # This acts as the retrievable reference for semantic search results.
    source_text = Column(String, nullable=False)
    
    # The embedding vector (pgvector)
    # Dimensions must match the configured embedding model
    embedding = Column(Vector(settings.EMBEDDING_DIMENSIONS), nullable=False)

    __table_args__ = (
        Index("ix_code_embeddings_snapshot_id", "snapshot_id"),
        Index("ix_code_embeddings_repo_snapshot", "repository_id", "snapshot_id"),
    )
