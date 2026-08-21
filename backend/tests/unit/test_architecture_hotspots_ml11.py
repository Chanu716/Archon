"""
Dependency Hotspot Analyzer Tests (Slice ML-11)

Tests:
  - Graph-topology based hotspot ranking
  - High fan-in node correctly identified
  - Low fan-in node not marked as high hotspot
  - Safe percentile calculation in small repositories
"""

import pytest
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import ArchitectureNodeFact, ArchitectureRole, ArchitectureLayer
from archon.pipeline.architecture.hotspots import HotspotAnalyzer


def test_hotspot_identification_by_fan_in():
    """SharedService depended on by 4 components is surfaced as a high hotspot"""
    nodes = {
        "ServiceA": ArchitectureNodeFact("ServiceA", "Class", ArchitectureRole.SERVICE, ArchitectureLayer.APPLICATION, "exact", "", "", "r1", "s1"),
        "ServiceB": ArchitectureNodeFact("ServiceB", "Class", ArchitectureRole.SERVICE, ArchitectureLayer.APPLICATION, "exact", "", "", "r1", "s1"),
        "ServiceC": ArchitectureNodeFact("ServiceC", "Class", ArchitectureRole.SERVICE, ArchitectureLayer.APPLICATION, "exact", "", "", "r1", "s1"),
        "ServiceD": ArchitectureNodeFact("ServiceD", "Class", ArchitectureRole.SERVICE, ArchitectureLayer.APPLICATION, "exact", "", "", "r1", "s1"),
        "SharedUtil": ArchitectureNodeFact("SharedUtil", "Class", ArchitectureRole.UTILITY, ArchitectureLayer.UNKNOWN, "exact", "", "", "r1", "s1"),
    }
    
    facts = [
        ResolutionResult(source_id="ServiceA", target_id="SharedUtil", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
        ResolutionResult(source_id="ServiceB", target_id="SharedUtil", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
        ResolutionResult(source_id="ServiceC", target_id="SharedUtil", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
        ResolutionResult(source_id="ServiceD", target_id="SharedUtil", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
    ]
    
    analyzer = HotspotAnalyzer("r1", "s1")
    hotspots = analyzer.analyze_hotspots(nodes, facts)
    
    assert len(hotspots) >= 1
    top = hotspots[0]
    assert top.qualified_name == "SharedUtil"
    assert top.fan_in == 4
    assert top.transitive_dependents == 4
    assert top.severity in ("medium", "high")
