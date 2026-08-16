import uuid
from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field

class EvidenceItem(BaseModel):
    evidence_id: str = Field(description="Unique identifier for this piece of evidence, e.g. E1")
    type: Literal["source", "graph", "metric", "git", "impact", "semantic"]
    repository_id: str
    snapshot_id: str
    entity_id: str | None = None
    source_reference: str
    content: str


class EvidenceBundle(BaseModel):
    repository_id: str
    snapshot_id: str
    evidence: List[EvidenceItem] = []


class AnalystResponse(BaseModel):
    """
    Structured output from the AI Analyst.
    """
    answer: str = Field(
        description="The detailed markdown answer to the user's question, grounded strictly in the provided evidence. Must contain inline citations using the exact evidence_id enclosed in brackets, e.g., [E1]."
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="AI interpretation of its own confidence based on the provided evidence. This is an interpretation, not a mathematical probability."
    )
    uncertainties: List[str] = Field(
        description="List of caveats, missing context, or relationships explicitly marked as 'unresolved' or 'inferred' in the evidence that reduce certainty."
    )
    referenced_evidence_ids: List[str] = Field(
        description="List of evidence_ids that were actually used and cited to construct the answer."
    )
