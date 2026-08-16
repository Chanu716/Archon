from pydantic import BaseModel, ConfigDict
from typing import Optional
import uuid
from datetime import datetime

class JobResponse(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    status: str
    current_stage: Optional[str] = None
    progress: float
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AnalyzeRequest(BaseModel):
    pass  # We can add options here later (like branch name)
