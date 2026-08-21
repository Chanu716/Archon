"""
Architecture Boundary & Transition Analyzer (Slice ML-11)

Evaluates cross-layer dependency flow against canonical architecture rules:
  - presentation   -> application    (allowed)
  - application    -> domain         (allowed)
  - application    -> infrastructure (allowed)
  - infrastructure -> domain         (allowed)
"""

from typing import Dict, List, Tuple, Optional
from archon.pipeline.architecture.models import (
    ArchitectureLayer,
    ArchitectureNodeFact,
)

# Canonical allowed layer transitions: (source_layer, target_layer)
ALLOWED_TRANSITIONS = {
    (ArchitectureLayer.PRESENTATION, ArchitectureLayer.APPLICATION),
    (ArchitectureLayer.APPLICATION, ArchitectureLayer.DOMAIN),
    (ArchitectureLayer.APPLICATION, ArchitectureLayer.INFRASTRUCTURE),
    (ArchitectureLayer.INFRASTRUCTURE, ArchitectureLayer.DOMAIN),
    # Same-layer communication is allowed
    (ArchitectureLayer.PRESENTATION, ArchitectureLayer.PRESENTATION),
    (ArchitectureLayer.APPLICATION, ArchitectureLayer.APPLICATION),
    (ArchitectureLayer.DOMAIN, ArchitectureLayer.DOMAIN),
    (ArchitectureLayer.INFRASTRUCTURE, ArchitectureLayer.INFRASTRUCTURE),
}


class ArchitectureBoundaryAnalyzer:
    """
    Evaluates whether directed relationships conform to architectural boundaries.
    """

    def is_transition_allowed(
        self,
        source_layer: ArchitectureLayer,
        target_layer: ArchitectureLayer
    ) -> bool:
        if source_layer == ArchitectureLayer.UNKNOWN or target_layer == ArchitectureLayer.UNKNOWN:
            return True
        return (source_layer, target_layer) in ALLOWED_TRANSITIONS
