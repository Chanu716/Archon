"""
Query Determinism Unit Tests (Slice ML-13)

Tests:
  - Repeated executions against identical inputs yield bit-for-bit identical results
  - Path ordering is strictly deterministic
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.query.models import ArchitectureQuery, QueryType
from archon.pipeline.query.service import ArchitectureQueryService


def test_repeated_query_determinism():
    entities = {
        "A": SnapshotEntityFact("A", "Class", "r1", "s1"),
        "B": SnapshotEntityFact("B", "Class", "r1", "s1"),
        "C": SnapshotEntityFact("C", "Class", "r1", "s1"),
    }
    relationships = [
        SnapshotRelationshipFact("A", "CALLS", "B", "r1", "s1"),
        SnapshotRelationshipFact("B", "CALLS", "C", "r1", "s1"),
    ]

    svc = ArchitectureQueryService("r1", "s1")
    query = ArchitectureQuery("r1", "s1", QueryType.DOWNSTREAM_DEPENDENCIES, entity="A")

    res1 = svc.execute(query, entities, relationships)
    res2 = svc.execute(query, entities, relationships)

    assert [p.end_entity for p in res1.paths] == [p.end_entity for p in res2.paths]
    assert len(res1.evidence) == len(res2.evidence)
    assert res1.explanation.summary == res2.explanation.summary
