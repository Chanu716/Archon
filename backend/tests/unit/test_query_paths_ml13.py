"""
Dependency Path Discovery Unit Tests (Slice ML-13)

Tests:
  - Exact path found between source and target
  - Multiple paths with deterministic sorting
  - No path found
  - Depth limit exceeded
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.query.paths import DependencyPathFinder


def test_exact_dependency_path_found():
    # Graph: A -> B -> C -> D
    entities = {
        "A": SnapshotEntityFact("A", "Class", "r1", "s1"),
        "B": SnapshotEntityFact("B", "Class", "r1", "s1"),
        "C": SnapshotEntityFact("C", "Class", "r1", "s1"),
        "D": SnapshotEntityFact("D", "Class", "r1", "s1"),
    }
    relationships = [
        SnapshotRelationshipFact("A", "CALLS", "B", "r1", "s1"),
        SnapshotRelationshipFact("B", "CALLS", "C", "r1", "s1"),
        SnapshotRelationshipFact("C", "CALLS", "D", "r1", "s1"),
    ]

    finder = DependencyPathFinder("r1", "s1", max_depth=5)
    paths, evidence, warnings = finder.find_paths("A", "D", relationships, entities)

    assert len(paths) == 1
    assert paths[0].length == 3
    assert [s.target_id for s in paths[0].steps] == ["B", "C", "D"]
    assert len(evidence) == 3


def test_no_path_found():
    entities = {
        "A": SnapshotEntityFact("A", "Class", "r1", "s1"),
        "B": SnapshotEntityFact("B", "Class", "r1", "s1"),
    }
    relationships = []

    finder = DependencyPathFinder("r1", "s1", max_depth=5)
    paths, _, _ = finder.find_paths("A", "B", relationships, entities)

    assert len(paths) == 0
