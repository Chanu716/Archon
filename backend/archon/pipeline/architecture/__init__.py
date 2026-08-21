"""
Archon Architecture Intelligence Engine (Slice ML-11)
"""

from archon.pipeline.architecture.models import (
    ArchitectureRole,
    ArchitectureLayer,
    ArchitectureNodeFact,
    ArchitectureCycle,
    HotspotFact,
    OrphanFact,
    ArchitectureViolation,
    ArchitectureAnalysisResult,
    ROLE_TO_LAYER,
)
from archon.pipeline.architecture.classifier import ArchitectureClassifier
from archon.pipeline.architecture.boundaries import ArchitectureBoundaryAnalyzer, ALLOWED_TRANSITIONS
from archon.pipeline.architecture.cycles import CycleDetector
from archon.pipeline.architecture.hotspots import HotspotAnalyzer
from archon.pipeline.architecture.orphans import OrphanAnalyzer
from archon.pipeline.architecture.violations import ArchitectureViolationAnalyzer
from archon.pipeline.architecture.service import ArchitectureIntelligenceService

__all__ = [
    "ArchitectureRole",
    "ArchitectureLayer",
    "ArchitectureNodeFact",
    "ArchitectureCycle",
    "HotspotFact",
    "OrphanFact",
    "ArchitectureViolation",
    "ArchitectureAnalysisResult",
    "ROLE_TO_LAYER",
    "ArchitectureClassifier",
    "ArchitectureBoundaryAnalyzer",
    "ALLOWED_TRANSITIONS",
    "CycleDetector",
    "HotspotAnalyzer",
    "OrphanAnalyzer",
    "ArchitectureViolationAnalyzer",
    "ArchitectureIntelligenceService",
]
