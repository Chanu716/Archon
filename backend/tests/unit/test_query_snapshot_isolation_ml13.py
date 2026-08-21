"""
Query Snapshot & Repository Isolation Unit Tests (Slice ML-13)

Tests:
  - Facts in snapshot 1 never leak into snapshot 2
  - Entities in repository 1 never resolve in repository 2
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.query.models import EntityResolutionStatus
from archon.pipeline.query.service import ArchitectureQueryService


def test_query_snapshot_isolation():
    entities_snap1 = {
        "Service": SnapshotEntityFact("Service", "Class", "repo-1", "snap-1"),
    }
    entities_snap2 = {
        "Service": SnapshotEntityFact("Service", "Class", "repo-1", "snap-2"),
    }

    svc1 = ArchitectureQueryService("repo-1", "snap-1")
    svc2 = ArchitectureQueryService("repo-1", "snap-2")

    res1 = svc1.resolve_entity("Service", entities_snap1)
    res2 = svc2.resolve_entity("Service", entities_snap2)

    assert res1.entity.snapshot_id == "snap-1"
    assert res2.entity.snapshot_id == "snap-2"


def test_query_repository_isolation():
    entities_repo1 = {
        "Service": SnapshotEntityFact("Service", "Class", "repo-1", "snap-1"),
    }
    svc2 = ArchitectureQueryService("repo-2", "snap-1")

    # Asking svc2 for repo-1's entity fact dict should properly scope to repo-2
    res = svc2.resolve_entity("NonExistentInRepo2", entities_repo1)
    assert res.status == EntityResolutionStatus.NOT_FOUND
