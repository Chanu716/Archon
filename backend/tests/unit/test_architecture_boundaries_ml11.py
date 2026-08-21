"""
Architecture Boundaries & Layer Transition Tests (Slice ML-11)

Tests:
  - Allowed transitions: presentation -> application, application -> domain/infrastructure, infrastructure -> domain
  - Prohibited transitions
  - Unknown layer transitions
"""

import pytest
from archon.pipeline.architecture.models import ArchitectureLayer
from archon.pipeline.architecture.boundaries import ArchitectureBoundaryAnalyzer


def test_allowed_layer_transitions():
    analyzer = ArchitectureBoundaryAnalyzer()
    
    assert analyzer.is_transition_allowed(ArchitectureLayer.PRESENTATION, ArchitectureLayer.APPLICATION) is True
    assert analyzer.is_transition_allowed(ArchitectureLayer.APPLICATION, ArchitectureLayer.DOMAIN) is True
    assert analyzer.is_transition_allowed(ArchitectureLayer.APPLICATION, ArchitectureLayer.INFRASTRUCTURE) is True
    assert analyzer.is_transition_allowed(ArchitectureLayer.INFRASTRUCTURE, ArchitectureLayer.DOMAIN) is True
    assert analyzer.is_transition_allowed(ArchitectureLayer.PRESENTATION, ArchitectureLayer.PRESENTATION) is True


def test_disallowed_layer_transitions():
    analyzer = ArchitectureBoundaryAnalyzer()
    
    # Layer skip: Presentation directly to Infrastructure
    assert analyzer.is_transition_allowed(ArchitectureLayer.PRESENTATION, ArchitectureLayer.INFRASTRUCTURE) is False
    
    # Reverse dependencies
    assert analyzer.is_transition_allowed(ArchitectureLayer.DOMAIN, ArchitectureLayer.PRESENTATION) is False
    assert analyzer.is_transition_allowed(ArchitectureLayer.INFRASTRUCTURE, ArchitectureLayer.PRESENTATION) is False
    assert analyzer.is_transition_allowed(ArchitectureLayer.DOMAIN, ArchitectureLayer.INFRASTRUCTURE) is False


def test_unknown_layer_does_not_create_false_violations():
    analyzer = ArchitectureBoundaryAnalyzer()
    
    assert analyzer.is_transition_allowed(ArchitectureLayer.UNKNOWN, ArchitectureLayer.APPLICATION) is True
    assert analyzer.is_transition_allowed(ArchitectureLayer.APPLICATION, ArchitectureLayer.UNKNOWN) is True
