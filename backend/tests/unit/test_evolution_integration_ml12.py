"""
Architecture Evolution Service Integration Tests (Slice ML-12)

Tests:
  - ArchitectureEvolutionService end-to-end comparison
  - Strict snapshot and repository isolation
  - Idempotency of results
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.evolution.service import ArchitectureEvolutionService
from archon.pipeline.architecture.models import (
    ArchitectureAnalysisResult,
    ArchitectureCycle,
    ArchitectureViolation,
)


def test_evolution_service_integration_and_isolation():
    base_entities = {
        "ServiceA": SnapshotEntityFact("ServiceA", "Class", "repo-1", "snap-1", architecture_role="service", architecture_layer="application"),
    }
    target_entities = {
        "ServiceA": SnapshotEntityFact("ServiceA", "Class", "repo-1", "snap-2", architecture_role="service", architecture_layer="application"),
        "ServiceB": SnapshotEntityFact("ServiceB", "Class", "repo-1", "snap-2", architecture_role="service", architecture_layer="application"),
    }

    base_rels = []
    target_rels = [
        SnapshotRelationshipFact("ServiceA", "CALLS", "ServiceB", "repo-1", "snap-2"),
    ]

    service = ArchitectureEvolutionService("repo-1", "snap-1", "snap-2")
    res1 = service.compare_snapshots(base_entities, target_entities, base_rels, target_rels)
    res2 = service.compare_snapshots(base_entities, target_entities, base_rels, target_rels)

    # Idempotency
    assert res1.summary == res2.summary
    assert res1.repository_id == "repo-1"
    assert res1.baseline_snapshot_id == "snap-1"
    assert res1.target_snapshot_id == "snap-2"


def test_repository_isolation():
    """Identical entity names in another repository are completely isolated"""
    entities_repo1 = {
        "OrderService": SnapshotEntityFact("OrderService", "Class", "repo-1", "snap-1"),
    }
    entities_repo2 = {
        "OrderService": SnapshotEntityFact("OrderService", "Class", "repo-2", "snap-1"),
    }

    svc1 = ArchitectureEvolutionService("repo-1", "snap-1", "snap-2")
    svc2 = ArchitectureEvolutionService("repo-2", "snap-1", "snap-2")

    res1 = svc1.compare_snapshots(entities_repo1, {}, [], [])
    res2 = svc2.compare_snapshots(entities_repo2, {}, [], [])

    assert res1.repository_id == "repo-1"
    assert res2.repository_id == "repo-2"
    assert res1.diff.removed_entities == ["OrderService"]
    assert res2.diff.removed_entities == ["OrderService"]
