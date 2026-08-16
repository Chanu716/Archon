from fastapi import BackgroundTasks
from typing import Callable, Any
import uuid
from archon.execution.base import ExecutionAdapter

class BackgroundTasksAdapter(ExecutionAdapter):
    """MVP: Uses FastAPI BackgroundTasks."""
    
    def __init__(self, background_tasks: BackgroundTasks):
        self.background_tasks = background_tasks

    async def submit(self, job_id: uuid.UUID, pipeline_fn: Callable[..., Any], *args, **kwargs) -> None:
        self.background_tasks.add_task(pipeline_fn, job_id, *args, **kwargs)
