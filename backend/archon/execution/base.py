from abc import ABC, abstractmethod
from typing import Callable, Any
import uuid

class ExecutionAdapter(ABC):
    @abstractmethod
    async def submit(self, job_id: uuid.UUID, pipeline_fn: Callable[..., Any], *args, **kwargs) -> None:
        """Schedule pipeline_fn to run asynchronously."""
        pass
