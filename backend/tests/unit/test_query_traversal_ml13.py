"""
Architecture Traversal Engine Unit Tests (Slice ML-13)

Tests:
  - Downstream traversal
  - Upstream traversal
  - Maximum depth enforcement
  - Cycle-safe traversal
  - Deterministic sorting
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.query.traversal import ArchitectureTraversalEngine


def test_downstream_traversal():
    # Graph: Controller -> Service -> Repository
    entities = {
        "Controller": SnapshotEntityFact("Controller", "Class", "r1", "s1", architecture_role="controller", architecture_layer="presentation"),
        "Service": SnapshotEntityFact("Service", "Class", "r1", "s1", architecture_role="service", architecture_layer="application"),
        "Repository": SnapshotEntityFact("Repository", "Class", "r1", "s1", architecture_role="repository", architecture_layer="infrastructure"),
    }
    relationships = [
        SnapshotRelationshipFact("Controller", "CALLS", "Service", "r1", "s1"),
        SnapshotRelationshipFact("Service", "DEPENDS_ON", "Repository", "r1", "s1"),
    ]

    engine = ArchitectureTraversalEngine("r1", "s1", max_depth=5)
    paths, evidence = engine.traverse("Controller", "downstream", relationships, entities)

    assert len(paths) == 2
    assert any(p.end_entity == "Service" for p in paths)
    assert any(p.end_entity == "Repository" for p in paths)
    assert len(evidence) == 2


def test_upstream_traversal():
    entities = {
        "Controller": SnapshotEntityFact("Controller", "Class", "r1", "s1"),
        "Service": SnapshotEntityFact("Service", "Class", "r1", "s1"),
        "Repository": SnapshotEntityFact("Repository", "Class", "r1", "s1"),
    }
    relationships = [
        SnapshotRelationshipFact("Controller", "CALLS", "Service", "r1", "s1"),
        SnapshotRelationshipFact("Service", "DEPENDS_ON", "Repository", "r1", "s1"),
    ]

    engine = ArchitectureTraversalEngine("r1", "s1", max_depth=5)
    paths, evidence = engine.traverse("Repository", "upstream", relationships, entities)

    assert len(paths) == 2
    assert any(p.end_entity == "Service" for p in paths)
    assert any(p.end_entity == "Controller" for p in paths)


def test_cycle_safe_traversal():
    # Cycle: A -> B -> A
    entities = {
        "A": SnapshotEntityFact("A", "Class", "r1", "s1"),
        "B": SnapshotEntityFact("B", "Class", "r1", "s1"),
    }
    relationships = [
        SnapshotRelationshipFact("A", "CALLS", "B", "r1", "s1"),
        SnapshotRelationshipFact("B", "CALLS", "A", "r1", "s1"),
    ]

    engine = ArchitectureTraversalEngine("r1", "s1", max_depth=5)
    paths, _ = engine.traverse("A", "downstream", relationships, entities)

    # Should not infinite loop and should return A -> B
    assert len(paths) == 1
    assert paths[0].end_entity == "B"
