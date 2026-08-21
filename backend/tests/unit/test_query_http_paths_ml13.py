"""
HTTP Architecture Request Tracer Unit Tests (Slice ML-13)

Tests:
  - Full request architecture tracing:
    UI Component -> Client -> Endpoint -> Handler -> Service -> Repository
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.query.paths import DependencyPathFinder


def test_http_request_architecture_tracing():
    entities = {
        "CheckoutButton": SnapshotEntityFact("CheckoutButton", "Class", "r1", "s1", architecture_role="component", architecture_layer="presentation"),
        "checkoutClient": SnapshotEntityFact("checkoutClient", "Function", "r1", "s1", architecture_role="client", architecture_layer="presentation"),
        "endpoint:POST:/api/v1/orders": SnapshotEntityFact("endpoint:POST:/api/v1/orders", "Endpoint", "r1", "s1"),
        "OrderController": SnapshotEntityFact("OrderController", "Class", "r1", "s1", architecture_role="controller", architecture_layer="presentation"),
        "OrderService": SnapshotEntityFact("OrderService", "Class", "r1", "s1", architecture_role="service", architecture_layer="application"),
        "OrderRepository": SnapshotEntityFact("OrderRepository", "Class", "r1", "s1", architecture_role="repository", architecture_layer="infrastructure"),
    }
    relationships = [
        SnapshotRelationshipFact("CheckoutButton", "CALLS", "checkoutClient", "r1", "s1"),
        SnapshotRelationshipFact("checkoutClient", "REQUESTS", "endpoint:POST:/api/v1/orders", "r1", "s1"),
        SnapshotRelationshipFact("endpoint:POST:/api/v1/orders", "HANDLED_BY", "OrderController", "r1", "s1"),
        SnapshotRelationshipFact("OrderController", "CALLS", "OrderService", "r1", "s1"),
        SnapshotRelationshipFact("OrderService", "DEPENDS_ON", "OrderRepository", "r1", "s1"),
    ]

    finder = DependencyPathFinder("r1", "s1", max_depth=6)
    chains, evidence, _ = finder.trace_http_architecture("CheckoutButton", relationships, entities)

    assert len(chains) == 1
    chain = chains[0]
    assert chain.length == 5
    assert [s.target_id for s in chain.steps] == [
        "checkoutClient",
        "endpoint:POST:/api/v1/orders",
        "OrderController",
        "OrderService",
        "OrderRepository",
    ]
