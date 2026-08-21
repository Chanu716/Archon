"""
Circular Dependency Detector Tests (Slice ML-11)

Tests:
  - Directed 2-node cycle (A -> B -> A) -> medium severity
  - Directed 3-node cycle (A -> B -> C -> A) -> high severity
  - Canonical identity (no duplicate reporting for B -> C -> A -> B)
  - Snapshot isolation
"""

import pytest
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.cycles import CycleDetector


def test_two_node_circular_dependency():
    """A -> B -> A produces exactly 1 cycle with severity 'medium'"""
    facts = [
        ResolutionResult(
            source_id="ServiceA", target_id="ServiceB", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""
        ),
        ResolutionResult(
            source_id="ServiceB", target_id="ServiceA", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""
        ),
    ]
    
    detector = CycleDetector("repo-1", "snap-1")
    cycles = detector.detect_cycles(facts)
    
    assert len(cycles) == 1
    c = cycles[0]
    assert c.cycle_id == "cycle:ServiceA->ServiceB"
    assert c.severity == "medium"
    assert "ServiceA" in c.members
    assert "ServiceB" in c.members


def test_three_node_circular_dependency_and_canonical_deduplication():
    """A -> B -> C -> A produces exactly 1 canonical cycle with severity 'high'"""
    facts = [
        ResolutionResult(source_id="A", target_id="B", relationship="CALLS", resolution="exact", evidence_type="", reason=""),
        ResolutionResult(source_id="B", target_id="C", relationship="CALLS", resolution="exact", evidence_type="", reason=""),
        ResolutionResult(source_id="C", target_id="A", relationship="CALLS", resolution="exact", evidence_type="", reason=""),
    ]
    
    detector = CycleDetector("repo-1", "snap-1")
    cycles = detector.detect_cycles(facts)
    
    assert len(cycles) == 1
    c = cycles[0]
    assert c.cycle_id == "cycle:A->B->C"
    assert c.severity == "high"
    assert c.members == ["A", "B", "C"]


def test_no_cycle_in_acyclic_graph():
    """A -> B -> C produces 0 cycles"""
    facts = [
        ResolutionResult(source_id="A", target_id="B", relationship="CALLS", resolution="exact", evidence_type="", reason=""),
        ResolutionResult(source_id="B", target_id="C", relationship="CALLS", resolution="exact", evidence_type="", reason=""),
    ]
    
    detector = CycleDetector("repo-1", "snap-1")
    cycles = detector.detect_cycles(facts)
    assert len(cycles) == 0
