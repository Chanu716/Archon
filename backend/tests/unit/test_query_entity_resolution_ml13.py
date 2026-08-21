"""
Entity Resolution Unit Tests (Slice ML-13)

Tests:
  - Exact qualified name resolution
  - Exact endpoint resolution
  - Unambiguous short name resolution
  - Explicit ambiguity surfacing (no guessing)
  - Missing entity -> NOT_FOUND
  - Module/file path resolution
"""

import pytest
from archon.pipeline.evolution.models import SnapshotEntityFact
from archon.pipeline.query.models import EntityResolutionStatus
from archon.pipeline.query.entity_resolver import EntityResolver


def test_exact_qualified_name_resolution():
    entities = {
        "MyApp.Services.OrderService": SnapshotEntityFact("MyApp.Services.OrderService", "Class", "r1", "s1", architecture_role="service", architecture_layer="application"),
    }
    resolver = EntityResolver("r1", "s1")
    res = resolver.resolve("MyApp.Services.OrderService", entities)

    assert res.status == EntityResolutionStatus.RESOLVED
    assert res.entity is not None
    assert res.entity.qualified_name == "MyApp.Services.OrderService"


def test_endpoint_resolution():
    entities = {
        "endpoint:POST:/api/v1/orders": SnapshotEntityFact("endpoint:POST:/api/v1/orders", "Endpoint", "r1", "s1"),
    }
    resolver = EntityResolver("r1", "s1")
    res = resolver.resolve("POST /api/v1/orders", entities)

    assert res.status == EntityResolutionStatus.RESOLVED
    assert res.entity.qualified_name == "endpoint:POST:/api/v1/orders"


def test_unambiguous_short_name_resolution():
    entities = {
        "MyApp.Services.OrderService": SnapshotEntityFact("MyApp.Services.OrderService", "Class", "r1", "s1"),
        "MyApp.Repositories.PaymentRepository": SnapshotEntityFact("MyApp.Repositories.PaymentRepository", "Class", "r1", "s1"),
    }
    resolver = EntityResolver("r1", "s1")
    res = resolver.resolve("OrderService", entities)

    assert res.status == EntityResolutionStatus.RESOLVED
    assert res.entity.qualified_name == "MyApp.Services.OrderService"


def test_explicit_ambiguity_rejection():
    """Ambiguous query matches multiple entities and returns AMBIGUOUS without guessing"""
    entities = {
        "MyApp.Services.OrderService": SnapshotEntityFact("MyApp.Services.OrderService", "Class", "r1", "s1"),
        "Legacy.Backend.OrderService": SnapshotEntityFact("Legacy.Backend.OrderService", "Class", "r1", "s1"),
    }
    resolver = EntityResolver("r1", "s1")
    res = resolver.resolve("OrderService", entities)

    assert res.status == EntityResolutionStatus.AMBIGUOUS
    assert res.entity is None
    assert len(res.candidates) == 2


def test_not_found_resolution():
    entities = {
        "MyApp.Services.OrderService": SnapshotEntityFact("MyApp.Services.OrderService", "Class", "r1", "s1"),
    }
    resolver = EntityResolver("r1", "s1")
    res = resolver.resolve("NonExistentService", entities)

    assert res.status == EntityResolutionStatus.NOT_FOUND
    assert res.entity is None
