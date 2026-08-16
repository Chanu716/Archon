from pydantic import BaseModel
from typing import List, Optional, Any, Dict
import uuid

class GraphNode(BaseModel):
    id: str
    labels: List[str]
    properties: Dict[str, Any]

class GraphEdge(BaseModel):
    id: str
    type: str
    source: str
    target: str
    properties: Dict[str, Any]

class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
