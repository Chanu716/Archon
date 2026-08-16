from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ToolResult(BaseModel):
    success: bool
    tool_name: str
    data: Dict[str, Any] | List[Any] | str
    truncated: bool = False
    error: Optional[str] = None

class SearchCodeInput(BaseModel):
    query: str = Field(description="The semantic search query to find related code entities.")
    limit: int = Field(default=5, description="Maximum number of results to return (max 10).")

class GetFileInput(BaseModel):
    relative_path: str = Field(description="The repository-relative path to the file.")

class GetFunctionInput(BaseModel):
    entity_id: str = Field(description="The qualified name or internal ID of the function.")

class GetClassInput(BaseModel):
    entity_id: str = Field(description="The qualified name or internal ID of the class.")

class GetGraphContextInput(BaseModel):
    entity_id: str = Field(description="The qualified name or internal ID of the entity.")
    relationship_types: Optional[List[str]] = Field(
        default=None, 
        description="Optional list of relationship types (e.g. CALLS, IMPORTS, CONTAINS, INHERITS)."
    )

class GetCallersInput(BaseModel):
    entity_id: str = Field(description="The qualified name or internal ID of the entity.")

class GetCalleesInput(BaseModel):
    entity_id: str = Field(description="The qualified name or internal ID of the entity.")

class GetImpactInput(BaseModel):
    entity_id: str = Field(description="The qualified name or internal ID of the entity.")
    direction: str = Field(
        default="both", 
        description="Direction of impact analysis: 'upstream', 'downstream', or 'both'."
    )
    depth: int = Field(default=5, description="Maximum depth for graph traversal.")

class GetMetricsInput(BaseModel):
    entity_id: str = Field(description="The qualified name or internal ID of the entity.")

class GetGitContextInput(BaseModel):
    file_path: str = Field(description="The repository-relative path to the file.")

class GetHotspotsInput(BaseModel):
    limit: int = Field(default=20, description="Maximum number of hotspots to return.")

class CompareSnapshotsInput(BaseModel):
    previous_snapshot_id: str = Field(description="The UUID of the previous snapshot.")
    current_snapshot_id: str = Field(description="The UUID of the current snapshot.")

class GetEvolutionTimelineInput(BaseModel):
    pass # No input required, gets timeline for current repo

class GetDriftFindingsInput(BaseModel):
    previous_snapshot_id: str = Field(description="The UUID of the previous snapshot.")
    current_snapshot_id: str = Field(description="The UUID of the current snapshot.")

class GetMetricTrendInput(BaseModel):
    entity_name: str = Field(description="The qualified name of the entity to analyze over time.")
