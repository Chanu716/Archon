from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from archon.db.session import async_session_factory
from archon.execution.background_tasks import BackgroundTasksAdapter
from fastapi import BackgroundTasks

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

def get_execution_adapter(background_tasks: BackgroundTasks) -> BackgroundTasksAdapter:
    return BackgroundTasksAdapter(background_tasks)
