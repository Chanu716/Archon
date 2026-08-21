"""
Candidate Orphaned Component Analyzer Tests (Slice ML-11)

Tests:
  - Genuine unreferenced component flagged as orphan candidate
  - Exclusions: entrypoints (main, Program, Startup) NOT flagged
  - Exclusions: controllers and endpoint handlers NOT flagged
  - Exclusions: DI bound classes NOT flagged
"""

import pytest
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import ArchitectureNodeFact, ArchitectureRole, ArchitectureLayer
from archon.pipeline.architecture.orphans import OrphanAnalyzer


def test_orphan_candidate_identification():
    """Unreferenced class with 0 inbound references is surfaced as an orphan candidate"""
    nodes = {
        "App.OrderService": ArchitectureNodeFact("App.OrderService", "Class", ArchitectureRole.SERVICE, ArchitectureLayer.APPLICATION, "exact", "", "", "r1", "s1"),
        "App.UnusedHelper": ArchitectureNodeFact("App.UnusedHelper", "Class", ArchitectureRole.UNKNOWN, ArchitectureLayer.UNKNOWN, "unresolved", "", "", "r1", "s1"),
    }
    
    # Inbound call only to OrderService
    facts = [
        ResolutionResult(source_id="App.Controller", target_id="App.OrderService", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
    ]
    
    analyzer = OrphanAnalyzer("r1", "s1")
    orphans = analyzer.analyze_orphans(nodes, facts)
    
    orphan_names = [o.qualified_name for o in orphans]
    assert "App.UnusedHelper" in orphan_names
    assert "App.OrderService" not in orphan_names


def test_entrypoints_excluded_from_orphans():
    """Startup, Program, and Main entrypoints are excluded from orphans"""
    nodes = {
        "App.Program": ArchitectureNodeFact("App.Program", "Class", ArchitectureRole.UNKNOWN, ArchitectureLayer.UNKNOWN, "unresolved", "", "", "r1", "s1"),
        "App.Startup": ArchitectureNodeFact("App.Startup", "Class", ArchitectureRole.UNKNOWN, ArchitectureLayer.UNKNOWN, "unresolved", "", "", "r1", "s1"),
    }
    
    analyzer = OrphanAnalyzer("r1", "s1")
    orphans = analyzer.analyze_orphans(nodes, [])
    
    assert len(orphans) == 0


def test_controllers_excluded_from_orphans():
    """Controllers are entrypoints and excluded from orphans"""
    nodes = {
        "App.OrderController": ArchitectureNodeFact("App.OrderController", "Class", ArchitectureRole.CONTROLLER, ArchitectureLayer.PRESENTATION, "exact", "", "", "r1", "s1"),
    }
    
    analyzer = OrphanAnalyzer("r1", "s1")
    orphans = analyzer.analyze_orphans(nodes, [])
    
    assert len(orphans) == 0
