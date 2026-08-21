"""
Architecture Query Service Dispatcher Tests (Slice ML-13)

Tests:
  - execute() dispatcher for all query types
  - Handling of missing parameters and error propagation
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.query.models import (
    ArchitectureQuery,
    QueryType,
    ResolutionConfidence,
)
from archon.pipeline.query.service import ArchitectureQueryService


def test_service_execute_upstream():
    entities = {
        "A": SnapshotEntityFact("A", "Class", "r1", "s1"),
        "B": SnapshotEntityFact("B", "Class", "r1", "s1"),
    }
    relationships = [
        SnapshotRelationshipFact("A", "CALLS", "B", "r1", "s1"),
    ]

    svc = ArchitectureQueryService("r1", "s1")
    query = ArchitectureQuery("r1", "s1", QueryType.UPSTREAM_DEPENDENTS, entity="B")
    res = svc.execute(query, entities, relationships)

    assert res.confidence == ResolutionConfidence.EXACT
    assert len(res.paths) == 1
    assert res.paths[0].start_entity == "A"


def test_service_execute_missing_entity():
    svc = ArchitectureQueryService("r1", "s1")
    query = ArchitectureQuery("r1", "s1", QueryType.DOWNSTREAM_DEPENDENCIES, entity="Unknown")
    res = svc.execute(query, {}, [])

    assert res.confidence == ResolutionConfidence.UNRESOLVED
    assert len(res.warnings) >= 1
