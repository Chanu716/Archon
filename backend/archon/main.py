from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from archon.config import settings
from archon.api.v1 import health, repositories, analysis, graph, metrics, impact, git, search, analyst, evolution, investigation, github_auth
from archon.db.neo4j import neo4j_driver
import structlog
import os

logger = structlog.get_logger(__name__)

def _get_allowed_origins() -> list[str]:
    """Build CORS allowed origins list from env or defaults."""
    env_origins = os.getenv("ALLOWED_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://nohcra.netlify.app",
    ]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("starting_archon_api", version=settings.ARCHON_VERSION)
    try:
        from archon.models.base import Base
        import archon.models.repository
        import archon.models.analysis_job
        import archon.models.metrics
        import archon.models.embedding
        import archon.models.git
        import archon.models.evolution
        import archon.models.impact
        import archon.models.investigation
        from archon.db.session import engine
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("postgres_tables_ready")
    except Exception as e:
        logger.warning("db_init_warning", error=str(e))

    try:
        neo4j_driver.connect()
        logger.info("neo4j_ready")
    except Exception as e:
        logger.warning("neo4j_connect_failed_at_startup", error=str(e))
    yield
    # Shutdown
    logger.info("shutting_down_archon_api")
    if neo4j_driver:
        await neo4j_driver.close()

app = FastAPI(
    title="Archon API",
    description="Archon - AI Software Architecture Intelligence",
    version=settings.ARCHON_VERSION,
    lifespan=lifespan
)

# CORS must be added BEFORE exception handlers so it wraps everything
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler that ensures CORS headers survive even on unhandled crashes."""
    origin = request.headers.get("origin", "")
    allowed = _get_allowed_origins()
    headers = {}
    if origin in allowed:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
        headers=headers,
    )

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(repositories.router, prefix="/api/v1", tags=["repositories"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(graph.router, prefix="/api/v1", tags=["graph"])
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])
app.include_router(impact.router, prefix="/api/v1", tags=["impact"])
app.include_router(git.router, prefix="/api/v1", tags=["git"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(analyst.router, prefix="/api/v1", tags=["analyst"])
app.include_router(evolution.router, prefix="/api/v1", tags=["evolution"])
app.include_router(investigation.router, prefix="/api/v1", tags=["investigation"])
app.include_router(github_auth.router, prefix="/api/v1", tags=["github"])

@app.get("/")
async def root():
    return {"message": "Welcome to Archon API", "version": settings.ARCHON_VERSION}
