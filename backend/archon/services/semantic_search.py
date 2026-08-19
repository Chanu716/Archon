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
            logger.warning("query_embedding_failed", error=str(e), repository_id=str(repository_id))
            query_embedding = [0.0] * 768

        is_zero_vector = not query_embedding or all(v == 0.0 for v in query_embedding)

        # 2. Similarity search using pgvector (or fallback text search if vector is zero)
        if not is_zero_vector:
            try:
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

                if rows:
                    results = []
                    for row in rows:
                        embedding, distance = row
                        similarity = max(0.0, min(1.0, 1.0 - (distance if distance is not None else 1.0)))
                        
                        results.append({
                            "entity": embedding.entity_id,
                            "entity_type": embedding.entity_type,
                            "file": embedding.file_path,
                            "name": embedding.entity_id,
                            "similarity": round(similarity, 3),
                            "source_reference": embedding.source_text,
                            "snapshot": str(embedding.snapshot_id)
                        })
                    return results
            except Exception as e:
                logger.warning("pgvector_search_failed_falling_back_to_text", error=str(e))

        # 3. Fallback: Search code entities by text/keyword in AST
        stmt = (
            select(CodeEmbedding)
            .where(CodeEmbedding.repository_id == repository_id)
            .where(CodeEmbedding.snapshot_id == snapshot_id)
            .where(
                CodeEmbedding.entity_id.ilike(f"%{query}%") | 
                CodeEmbedding.source_text.ilike(f"%{query}%")
            )
            .limit(limit)
        )
        if entity_types:
            stmt = stmt.where(CodeEmbedding.entity_type.in_(entity_types))

        result = await self.db.execute(stmt)
        embeddings = result.scalars().all()
        
        if embeddings:
            return [
                {
                    "entity": emb.entity_id,
                    "entity_type": emb.entity_type,
                    "file": emb.file_path,
                    "name": emb.entity_id,
                    "similarity": 0.85,
                    "source_reference": emb.source_text,
                    "snapshot": str(emb.snapshot_id)
                }
                for emb in embeddings
            ]

        # 4. Final Fallback: Query Neo4j Knowledge Graph directly
        try:
            from archon.db.neo4j import neo4j_driver
            neo4j_q = """
            MATCH (n {snapshot_id: $snapshot_id})
            WHERE (
                toLower(coalesce(n.qualified_name, '')) CONTAINS toLower($q)
                OR toLower(coalesce(n.name, '')) CONTAINS toLower($q)
                OR toLower(coalesce(n.path, '')) CONTAINS toLower($q)
                OR toLower(coalesce(n.docstring, '')) CONTAINS toLower($q)
            )
            AND NOT n:Repository
            RETURN n, labels(n)[0] as type LIMIT $limit
            """
            async with neo4j_driver.session() as session:
                res = await session.run(neo4j_q, snapshot_id=str(snapshot_id), q=query, limit=limit)
                records = await res.data()
                results = []
                for r in records:
                    node = r["n"]
                    props = dict(node.items())
                    name = props.get("name") or props.get("qualified_name") or props.get("path") or "Node"
                    results.append({
                        "entity": props.get("qualified_name") or name,
                        "entity_type": r["type"],
                        "file": props.get("path") or "",
                        "name": name,
                        "similarity": 0.88,
                        "source_reference": props.get("docstring") or f"{r['type']}: {name}",
                        "snapshot": str(snapshot_id)
                    })
                return results
        except Exception as e:
            logger.warning("neo4j_fallback_search_failed", error=str(e))
            return []
