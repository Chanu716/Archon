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
            user = (settings.NEO4J_USERNAME or settings.NEO4J_USER or "neo4j").strip()
            password = (settings.NEO4J_PASSWORD or "").strip()
            uri = (settings.NEO4J_URI or "").strip()
            
            self.driver = AsyncGraphDatabase.driver(
                uri,
                auth=(user, password),
            )
            logger.info("neo4j_connected", uri=uri, user=user, database=settings.NEO4J_DATABASE)
        except Exception as e:
            logger.error("neo4j_connection_failed", error=str(e))
            raise

    def session(self, **kwargs):
        """Open a session on the configured database."""
        if not self.driver:
            self.connect()
        db_name = (settings.NEO4J_DATABASE or "neo4j").strip()
        return self.driver.session(database=db_name, **kwargs)

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
    async with neo4j_driver.session() as session:
        yield session
