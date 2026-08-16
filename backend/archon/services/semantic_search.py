"""
Semantic Search Service
"""
import uuid
from typing import List, Dict, Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from archon.pipeline.embeddings.provider import get_embedding_provider
from archon.models.repository import AnalysisSnapshot
from archon.models.embedding import CodeEmbedding

logger = structlog.get_logger(__name__)

class SemanticSearchService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.provider = get_embedding_provider()

    async def search(
        self,
        repository_id: uuid.UUID,
        query: str,
        snapshot_id: uuid.UUID = None,
        limit: int = 10,
        entity_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes a semantic search against the specified repository snapshot.
        If no snapshot is provided, defaults to the latest snapshot.
        """
        if not snapshot_id:
            # Resolve latest snapshot
            result = await self.db.execute(
                select(AnalysisSnapshot)
                .where(AnalysisSnapshot.repository_id == repository_id)
                .where(AnalysisSnapshot.is_latest == True)
                .order_by(AnalysisSnapshot.analyzed_at.desc())
            )
            snapshot = result.scalars().first()
            if not snapshot:
                return []
            snapshot_id = snapshot.id

        # 1. Embed the query
        try:
            query_embedding = await self.provider.embed(query)
        except Exception as e:
            logger.error("query_embedding_failed", error=str(e), repository_id=str(repository_id))
            raise ValueError(f"Failed to generate embedding for query: {str(e)}")

        # 2. Similarity search using pgvector
        # Calculate cosine distance
        distance_col = CodeEmbedding.embedding.cosine_distance(query_embedding).label('distance')
        
        stmt = (
            select(CodeEmbedding, distance_col)
            .where(CodeEmbedding.repository_id == repository_id)
            .where(CodeEmbedding.snapshot_id == snapshot_id)
        )
        
        if entity_types:
            stmt = stmt.where(CodeEmbedding.entity_type.in_(entity_types))
            
        stmt = stmt.order_by(distance_col).limit(limit)

        result = await self.db.execute(stmt)
        rows = result.all()

        # 3. Format results
        results = []
        for row in rows:
            embedding, distance = row
            # pgvector distance is cosine distance (0 means exact match).
            # Convert to similarity (1 - distance)
            similarity = 1.0 - distance
            
            results.append({
                "entity": embedding.entity_id,
                "entity_type": embedding.entity_type,
                "file": embedding.file_path,
                "name": embedding.entity_id,
                "similarity": similarity,
                "source_reference": embedding.source_text,
                "snapshot": str(embedding.snapshot_id)
            })

        return results
