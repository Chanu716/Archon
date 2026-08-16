from neo4j import AsyncGraphDatabase, AsyncDriver
from archon.config import settings
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)

class Neo4jConnectionManager:
    def __init__(self):
        self.driver: Optional[AsyncDriver] = None

    def connect(self):
        try:
            self.driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            logger.info("neo4j_connected", uri=settings.NEO4J_URI)
        except Exception as e:
            logger.error("neo4j_connection_failed", error=str(e))
            raise

    async def close(self):
        if self.driver:
            await self.driver.close()
            logger.info("neo4j_connection_closed")

    async def verify_connectivity(self):
        if not self.driver:
            self.connect()
        await self.driver.verify_connectivity()

# Global singleton — connect() is called explicitly by the application lifespan,
# not at import time, to allow tests to import this module without a live Neo4j.
neo4j_driver = Neo4jConnectionManager()

async def get_neo4j_session():
    if not neo4j_driver.driver:
        neo4j_driver.connect()
    async with neo4j_driver.driver.session() as session:
        yield session
