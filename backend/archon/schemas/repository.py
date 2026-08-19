from pydantic import BaseModel, HttpUrl, ConfigDict
from typing import Optional, List
import uuid
from datetime import datetime

class RepositoryCreate(BaseModel):
    source_url: HttpUrl
    github_token: Optional[str] = None  # OAuth token for private repo access

class RepositoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    source_type: str
    source_url: str
    detected_languages: Optional[List[str]] = None
    last_analyzed_at: Optional[datetime] = None
    last_analyzed_commit: Optional[str] = None
    created_at: datetime
    # Whether a completed analysis snapshot exists for this repo
    has_snapshot: bool = False

    model_config = ConfigDict(from_attributes=True)
