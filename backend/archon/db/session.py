from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from archon.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_size=5,        # Supabase free: max 10 connections total
    max_overflow=5,
    pool_pre_ping=True,  # Auto-reconnect on dropped connections
    pool_recycle=300,    # Recycle connections every 5 min to avoid stale sockets
)

async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

async def get_db_session():
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Alias so that any file importing from archon.db.session still works
get_db = get_db_session
