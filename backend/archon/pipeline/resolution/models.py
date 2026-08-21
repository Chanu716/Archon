"""
Cross-Language Resolution Models (ML-4)

Defines pure domain/runtime models for deterministic cross-language and
cross-extension resolution evidence and results.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List


class ResolutionType(str, Enum):
    MODULE_IMPORT = "module_import"
    SYMBOL_CALL = "symbol_call"
    HTTP_ENDPOINT = "http_endpoint"


class ResolutionConfidence(str, Enum):
    EXACT = "exact"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


@dataclass
class ResolutionCandidate:
    """A candidate target entity discovered during resolution."""
    entity_id: str
    entity_type: str  # "Module" | "Class" | "Function" | "Endpoint"
    language: str
    file_path: str
    confidence: ResolutionConfidence = ResolutionConfidence.UNRESOLVED
    evidence: Optional[str] = None


@dataclass
class ResolutionResult:
    """
    The deterministic result of resolving a relationship across files or languages.
    """
    source_id: str
    target_id: str
    relationship: str  # "IMPORTS", "CALLS", "REQUESTS", "HANDLED_BY"
    resolution: str    # "exact", "inferred", "unresolved"
    evidence_type: str # e.g. "relative_import", "explicit_import", "static_http_route"
    reason: str
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    source_file: Optional[str] = None
    target_file: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
