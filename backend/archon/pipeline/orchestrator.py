import uuid
import asyncio
from typing import Callable, Awaitable, List
import structlog
from archon.pipeline.ingestion.github import clone_github_repo
from archon.pipeline.ingestion.local import import_local_repo
from archon.pipeline.ingestion.scanner import scan_directory
from archon.pipeline.parsers.registry import registry
from archon.pipeline.parsers.base import ParsedFile, SkipRecord
import archon.pipeline.parsers.python.parser  # Auto-register python parser
import archon.pipeline.parsers.typescript.parser  # Auto-register typescript parser
import archon.pipeline.parsers.javascript.parser  # Auto-register javascript parser
import archon.pipeline.parsers.java.parser  # Auto-register java parser
import archon.pipeline.parsers.csharp.parser  # Auto-register csharp parser
import archon.pipeline.parsers.go.parser  # Auto-register go parser
import archon.pipeline.parsers.rust.parser  # Auto-register rust parser
from archon.pipeline.graph.builder import GraphBuilder
from archon.pipeline.resolution import CrossLanguageResolver
from archon.pipeline.analysis.analyzer import StaticAnalyzer
from archon.pipeline.analysis.git_analyzer import GitAnalyzer
from archon.pipeline.analysis.risk_calculator import RiskCalculator
from archon.pipeline.embeddings.generator import EmbeddingGenerator
from archon.services.storage_service import RepositoryStorageService
from archon.db.session import async_session_factory
from archon.models.repository import AnalysisSnapshot
from archon.config import settings

logger = structlog.get_logger(__name__)

async def run_analysis_pipeline(
    repository_id: uuid.UUID,
    job_id: uuid.UUID,
    source_url: str,
    source_type: str,
    progress_callback: Callable[[uuid.UUID, float, str], Awaitable[None]]
):
    """
    Framework-independent pipeline orchestrator.
    Progress callback is the only coupling point.
    """
    try:
        await progress_callback(job_id, 0.0, "ingestion")
        
        storage_service = RepositoryStorageService()
        target_path = storage_service.get_repository_path(repository_id)
        
        if source_type == "github":
            ingestion_result = clone_github_repo(source_url, target_path, repository_id)
        elif source_type == "local":
            ingestion_result = import_local_repo(source_url, target_path, repository_id)
        else:
            raise ValueError(f"Unsupported source_type: {source_type}")
            
        await progress_callback(job_id, 10.0, "parsing")
        
        total_files = len(ingestion_result.files)
        for idx, file_path in enumerate(ingestion_result.files):
            # Yield periodically to allow event loop to process health checks and polling requests
            if idx % 5 == 0:
                await asyncio.sleep(0)
                progress_pct = 10.0 + (float(idx) / max(total_files, 1)) * 20.0
                await progress_callback(job_id, progress_pct, "parsing")

            extension = file_path.suffix
            parser = registry.get_parser(extension)
            if parser is None:
                # ML-1: Structured skip — no parser registered for this extension.
                # This is expected for config files, images, etc.
                skip_records.append(SkipRecord(
                    path=str(file_path),
                    extension=extension,
                    reason="unsupported_extension",
                ))
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                # Make path relative to repository root for consistency
                rel_path = file_path.relative_to(target_path).as_posix()
                parsed_file = parser.parse_file(rel_path, content)
                parsed_files.append(parsed_file)
            except Exception as e:
                # Per-file failure must not abort the entire pipeline.
                logger.error(
                    "parse_file_error",
                    path=str(file_path),
                    language=parser.language if parser else "unknown",
                    error=str(e)
                )
                skip_records.append(SkipRecord(
                    path=str(file_path),
                    extension=extension,
                    reason=f"parse_error: {e}",
                ))

        logger.info(
            "parsing_complete",
            parsed_count=len(parsed_files),
            skipped_count=len(skip_records),
            registered_languages=sorted(registry.supported_extensions()),
        )
                
        # Persist AnalysisSnapshot to Postgres
        snapshot = AnalysisSnapshot(
            repository_id=repository_id,
            analysis_job_id=job_id,
            commit_sha=ingestion_result.commit_sha,
            archon_version=settings.ARCHON_VERSION,
            parser_version="1.0.0", # Hardcoded for MVP
            is_latest=True
        )
        async with async_session_factory() as db:
            from sqlalchemy import update
            await db.execute(
                update(AnalysisSnapshot)
                .where(AnalysisSnapshot.repository_id == repository_id)
                .values(is_latest=False)
            )
            db.add(snapshot)
            await db.commit()
            await db.refresh(snapshot)
            snapshot_id = snapshot.id
        
        await progress_callback(job_id, 35.0, "git_analysis")
        git_analyzer = GitAnalyzer(
            repository_id=repository_id,
            snapshot_id=snapshot.id,
            managed_path=str(target_path),
            snapshot_commit_sha=ingestion_result.commit_sha
        )
        await git_analyzer.run()
        
        await progress_callback(job_id, 50.0, "graph_construction")
        
        graph_builder = GraphBuilder(
            repository_id=repository_id, 
            snapshot_id=snapshot_id, 
            commit_sha=ingestion_result.commit_sha or "unknown"
        )
        await graph_builder.build(parsed_files)
        
        await progress_callback(job_id, 58.0, "cross_language_resolution")
        cross_resolver = CrossLanguageResolver(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            target_path=target_path
        )
        await cross_resolver.resolve_and_persist(parsed_files)
        
        await progress_callback(job_id, 65.0, "static_analysis")
        analyzer = StaticAnalyzer(repository_id, snapshot.id)
        await analyzer.run_analysis()
        
        await progress_callback(job_id, 80.0, "graph_analysis")
        # Skipping for Slice 1
        
        await progress_callback(job_id, 85.0, "embedding")
        embedder = EmbeddingGenerator(
            repository_id=repository_id,
            snapshot_id=snapshot.id
        )
        await embedder.generate_and_store(parsed_files)
        
        await progress_callback(job_id, 92.0, "risk_calculation")
        risk_calculator = RiskCalculator(snapshot_id=snapshot.id)
        await risk_calculator.calculate()
        
        await progress_callback(job_id, 98.0, "finalizing")
        # Normally save metrics here
        
        await progress_callback(job_id, 100.0, "completed")
        logger.info("pipeline_completed", job_id=str(job_id))
        
    except Exception as e:
        logger.error("pipeline_failed", job_id=str(job_id), error=str(e))
        await progress_callback(job_id, -1.0, "failed", str(e))
        raise
