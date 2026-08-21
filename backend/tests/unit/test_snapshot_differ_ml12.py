"""
Snapshot Differ Unit Tests (Slice ML-12)

Tests:
  - Added entities
  - Removed entities
  - Unchanged entities
  - Modified entities (role and layer changes)
  - Direction-sensitive relationship additions & removals
  - Resolution confidence changes (unresolved -> exact, exact -> unresolved)
"""

import pytest
from archon.pipeline.evolution.models import (
    ChangeType,
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.evolution.differ import SnapshotDiffer


def test_entity_lifecycle_diff():
    """Verifies added, removed, unchanged, and modified entity detection"""
    base_entities = {
        "App.UnchangedService": SnapshotEntityFact("App.UnchangedService", "Class", "repo-1", "snap-1", architecture_role="service", architecture_layer="application"),
        "App.OldHelper": SnapshotEntityFact("App.OldHelper", "Class", "repo-1", "snap-1", architecture_role="unknown", architecture_layer="unknown"),
        "App.MutatedComponent": SnapshotEntityFact("App.MutatedComponent", "Class", "repo-1", "snap-1", architecture_role="service", architecture_layer="application"),
    }

    target_entities = {
        "App.UnchangedService": SnapshotEntityFact("App.UnchangedService", "Class", "repo-1", "snap-2", architecture_role="service", architecture_layer="application"),
        "App.NewGateway": SnapshotEntityFact("App.NewGateway", "Class", "repo-1", "snap-2", architecture_role="gateway", architecture_layer="infrastructure"),
        "App.MutatedComponent": SnapshotEntityFact("App.MutatedComponent", "Class", "repo-1", "snap-2", architecture_role="repository", architecture_layer="infrastructure"),
    }

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots(base_entities, target_entities, [], [])

    assert "App.NewGateway" in diff.added_entities
    assert "App.OldHelper" in diff.removed_entities
    assert "App.MutatedComponent" in diff.modified_entities
    assert diff.entity_diffs["App.UnchangedService"].change_type == ChangeType.UNCHANGED

    # Check field changes
    mutated_diff = diff.entity_diffs["App.MutatedComponent"]
    assert mutated_diff.field_changes["architecture_role"] == ("service", "repository")
    assert mutated_diff.field_changes["architecture_layer"] == ("application", "infrastructure")


def test_directional_relationship_diff():
    """Verifies direction-sensitive relationship diffing"""
    base_rels = [
        SnapshotRelationshipFact("Controller", "CALLS", "ServiceA", "repo-1", "snap-1", resolution="exact"),
    ]
    target_rels = [
        SnapshotRelationshipFact("Controller", "CALLS", "ServiceB", "repo-1", "snap-2", resolution="exact"),
        # Reverse edge
        SnapshotRelationshipFact("ServiceA", "CALLS", "Controller", "repo-1", "snap-2", resolution="exact"),
    ]

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots({}, {}, base_rels, target_rels)

    assert "Controller->CALLS->ServiceA" in diff.removed_relationships
    assert "Controller->CALLS->ServiceB" in diff.added_relationships
    assert "ServiceA->CALLS->Controller" in diff.added_relationships


def test_resolution_confidence_diff():
    """Verifies resolution confidence improvement and regression detection"""
    base_rels = [
        SnapshotRelationshipFact("A", "CALLS", "B", "repo-1", "snap-1", resolution="unresolved"),
        SnapshotRelationshipFact("C", "DEPENDS_ON", "D", "repo-1", "snap-1", resolution="exact"),
    ]
    target_rels = [
        SnapshotRelationshipFact("A", "CALLS", "B", "repo-1", "snap-2", resolution="exact"),
        SnapshotRelationshipFact("C", "DEPENDS_ON", "D", "repo-1", "snap-2", resolution="inferred"),
    ]

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots({}, {}, base_rels, target_rels)

    assert len(diff.resolution_changes) == 2
    res_map = {r.canonical_id: r.resolution_change for r in diff.resolution_changes}
    assert res_map["A->CALLS->B"] == ("unresolved", "exact")
    assert res_map["C->DEPENDS_ON->D"] == ("exact", "inferred")
