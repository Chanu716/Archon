"""
Architecture Change Analyzer Unit Tests (Slice ML-12)

Tests:
  - Role modifications (Service -> Repository)
  - Layer transitions (Application -> Infrastructure)
  - Dependency additions & removals
  - HTTP Endpoint additions & removals
  - Resolution improvements & degradations
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.evolution.differ import SnapshotDiffer
from archon.pipeline.evolution.changes import ArchitectureChangeAnalyzer


def test_semantic_architecture_changes():
    base_entities = {
        "OrderService": SnapshotEntityFact("OrderService", "Class", "repo-1", "snap-1", architecture_role="service", architecture_layer="application"),
        "endpoint:POST:/api/v1/orders": SnapshotEntityFact("endpoint:POST:/api/v1/orders", "Endpoint", "repo-1", "snap-1"),
    }
    target_entities = {
        "OrderService": SnapshotEntityFact("OrderService", "Class", "repo-1", "snap-2", architecture_role="repository", architecture_layer="infrastructure"),
        "endpoint:POST:/api/v2/orders": SnapshotEntityFact("endpoint:POST:/api/v2/orders", "Endpoint", "repo-1", "snap-2"),
    }

    base_rels = [
        SnapshotRelationshipFact("OrderController", "DEPENDS_ON", "OldRepo", "repo-1", "snap-1", resolution="exact"),
        SnapshotRelationshipFact("OrderService", "CALLS", "PaymentGateway", "repo-1", "snap-1", resolution="unresolved"),
    ]
    target_rels = [
        SnapshotRelationshipFact("OrderController", "DEPENDS_ON", "NewRepo", "repo-1", "snap-2", resolution="exact"),
        SnapshotRelationshipFact("OrderService", "CALLS", "PaymentGateway", "repo-1", "snap-2", resolution="exact"),
    ]

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots(base_entities, target_entities, base_rels, target_rels)

    analyzer = ArchitectureChangeAnalyzer("repo-1", "snap-1", "snap-2")
    changes = analyzer.analyze_changes(diff)

    categories = [c.category for c in changes]
    assert "role_change" in categories
    assert "layer_change" in categories
    assert "endpoint_added" in categories
    assert "endpoint_removed" in categories
    assert "dependency_added:depends_on" in categories
    assert "dependency_removed:depends_on" in categories
    assert "resolution_improved" in categories
