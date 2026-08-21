"""
Change Impact Analyzer Unit Tests (Slice ML-12)

Tests:
  - Direct dependents and dependencies
  - Bounded transitive impact reachability
  - Blast radius score calculation
"""

import pytest
from archon.pipeline.evolution.models import (
    SnapshotEntityFact,
    SnapshotRelationshipFact,
)
from archon.pipeline.evolution.differ import SnapshotDiffer
from archon.pipeline.evolution.impact import ChangeImpactAnalyzer


def test_bounded_transitive_change_impact():
    """Verifies that changing a component computes its direct and transitive blast radius"""
    # Graph: A -> B -> C -> D
    # If B is modified, direct dependents: A; direct dependencies: C; transitive: D
    base_rels = [
        SnapshotRelationshipFact("A", "CALLS", "B", "repo-1", "snap-1"),
        SnapshotRelationshipFact("B", "CALLS", "C", "repo-1", "snap-1"),
        SnapshotRelationshipFact("C", "CALLS", "D", "repo-1", "snap-1"),
    ]
    target_rels = [
        SnapshotRelationshipFact("A", "CALLS", "B", "repo-1", "snap-2"),
        SnapshotRelationshipFact("B", "CALLS", "C", "repo-1", "snap-2"),
        SnapshotRelationshipFact("C", "CALLS", "D", "repo-1", "snap-2"),
    ]

    base_entities = {
        "B": SnapshotEntityFact("B", "Class", "repo-1", "snap-1", architecture_role="service", architecture_layer="application"),
    }
    target_entities = {
        "B": SnapshotEntityFact("B", "Class", "repo-1", "snap-2", architecture_role="repository", architecture_layer="infrastructure"),
    }

    differ = SnapshotDiffer("repo-1", "snap-1", "snap-2")
    diff = differ.diff_snapshots(base_entities, target_entities, base_rels, target_rels)

    analyzer = ChangeImpactAnalyzer("repo-1", "snap-1", "snap-2", max_depth=5)
    impact_facts, _ = analyzer.analyze_impact_and_risk(diff, [], None)

    assert len(impact_facts) == 1
    b_impact = impact_facts[0]
    assert b_impact.changed_entity == "B"
    assert "A" in b_impact.direct_dependents
    assert "C" in b_impact.direct_dependencies
    assert "D" in b_impact.transitive_impacted_nodes
    assert b_impact.blast_radius_score >= 3
