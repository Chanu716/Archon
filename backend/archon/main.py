from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from archon.config import settings
from archon.api.v1 import health, repositories, analysis, graph, metrics, impact, git, search, analyst, evolution, investigation
from archon.db.neo4j import neo4j_driver
import structlog

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("starting_archon_api", version=settings.ARCHON_VERSION)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.get("/")
async def root():
    return {"message": "Welcome to Archon API", "version": settings.ARCHON_VERSION}
