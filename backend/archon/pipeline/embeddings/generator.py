"""
Embedding Generator Service

Constructs semantic units from the AST/parsed files and generates embeddings
in batches. Saves the resulting vectors to PostgreSQL.
"""
import uuid
import asyncio
from typing import List, Dict, Any
import structlog
from archon.pipeline.parsers.base import ParsedFile
from archon.pipeline.embeddings.provider import get_embedding_provider
from archon.db.session import async_session_factory
from archon.models.embedding import CodeEmbedding

logger = structlog.get_logger(__name__)

class EmbeddingGenerator:
    def __init__(
        self,
        repository_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        batch_size: int = 100,
        max_retries: int = 2
    ):
        self.repository_id = repository_id
        self.snapshot_id = snapshot_id
        self.batch_size = batch_size
        self.max_retries = max_retries
        try:
            self.provider = get_embedding_provider()
        except Exception as e:
            logger.error("embedding_provider_initialization_failed", error=str(e))
            self.provider = None

    async def generate_and_store(self, parsed_files: List[ParsedFile]) -> bool:
        """
        Main entry point for generating embeddings for a given set of parsed files.
        """
        if not self.provider:
            logger.error("embedding_generation_skipped_no_provider", snapshot_id=str(self.snapshot_id))
            return False

        semantic_units = self._extract_semantic_units(parsed_files)
        logger.info("extracted_semantic_units", count=len(semantic_units), snapshot_id=str(self.snapshot_id))
        
        if not semantic_units:
            return True

        # Process in batches
        batches = [semantic_units[i:i + self.batch_size] for i in range(0, len(semantic_units), self.batch_size)]
        
        success_count = 0
        failure_count = 0

        async with async_session_factory() as db:
            for i, batch in enumerate(batches):
                texts = [unit["source_text"] for unit in batch]
                
                # Retry logic for embedding provider failures
                embeddings = None
                for attempt in range(self.max_retries + 1):
                    try:
                        embeddings = await self.provider.embed_batch(texts)
                        break
                    except Exception as e:
                        if attempt < self.max_retries:
                            logger.warning(
                                "embedding_batch_failed_retrying", 
                                batch_index=i, attempt=attempt+1, error=str(e)
                            )
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            logger.error("embedding_batch_failed_final", batch_index=i, error=str(e))
                            
                if embeddings:
                    # Save successful batch to DB
                    db_records = []
                    for unit, vector in zip(batch, embeddings):
                        record = CodeEmbedding(
                            repository_id=self.repository_id,
                            snapshot_id=self.snapshot_id,
                            entity_id=unit["entity_id"],
                            entity_type=unit["entity_type"],
                            file_path=unit["file_path"],
                            source_text=unit["source_text"],
                            embedding=vector
                        )
                        db_records.append(record)
                    
                    db.add_all(db_records)
                    await db.commit()
                    success_count += len(batch)
                else:
                    failure_count += len(batch)
                    
        logger.info(
            "embedding_generation_complete", 
            success_count=success_count, 
            failure_count=failure_count,
            snapshot_id=str(self.snapshot_id)
        )
        return failure_count == 0

    def _extract_semantic_units(self, parsed_files: List[ParsedFile]) -> List[Dict[str, Any]]:
        """
        Extract deterministic semantic units from parsed files.
        We format the contextual string sent to the embedding provider here.
        """
        units = []
        
        for pfile in parsed_files:
            # Module / File
            # ML-1: Use module_name provided by the parser (language-neutral).
            # Never re-derive module names from paths here — that is parser-specific logic.
            module_name = pfile.module_name or pfile.path
                
            module_doc = pfile.docstring or "No module docstring provided."
            module_text = f"Module: {module_name}\nFile: {pfile.path}\n\nDocstring:\n{module_doc}"
            
            units.append({
                "entity_id": module_name,
                "entity_type": "Module",
                "file_path": pfile.path,
                "source_text": module_text
            })
            
            # Classes
            for cls in pfile.classes:
                cls_doc = cls.docstring or "No class docstring provided."
                bases = f"Inherits from: {', '.join(cls.base_classes)}" if cls.base_classes else "No base classes."
                methods = f"Methods: {', '.join([m.name for m in cls.methods])}" if cls.methods else "No methods."
                
                cls_text = (
                    f"Class: {cls.name}\n"
                    f"Module: {module_name}\n"
                    f"File: {pfile.path}\n"
                    f"{bases}\n"
                    f"{methods}\n\n"
                    f"Docstring:\n{cls_doc}"
                )
                
                units.append({
                    "entity_id": cls.qualified_name,
                    "entity_type": "Class",
                    "file_path": pfile.path,
                    "source_text": cls_text
                })
                
                # Methods
                for method in cls.methods:
                    method_doc = method.docstring or "No method docstring provided."
                    method_text = (
                        f"Method: {method.name}\n"
                        f"Class: {cls.name}\n"
                        f"Module: {module_name}\n"
                        f"File: {pfile.path}\n\n"
                        f"Docstring:\n{method_doc}"
                    )
                    
                    units.append({
                        "entity_id": method.qualified_name,
                        "entity_type": "Method",
                        "file_path": pfile.path,
                        "source_text": method_text
                    })
                    
            # Functions
            for func in pfile.functions:
                func_doc = func.docstring or "No function docstring provided."
                func_text = (
                    f"Function: {func.name}\n"
                    f"Module: {module_name}\n"
                    f"File: {pfile.path}\n\n"
                    f"Docstring:\n{func_doc}"
                )
                
                units.append({
                    "entity_id": func.qualified_name,
                    "entity_type": "Function",
                    "file_path": pfile.path,
                    "source_text": func_text
                })
                
        return units
