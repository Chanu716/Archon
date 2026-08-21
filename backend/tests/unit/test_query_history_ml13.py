"""
Architecture History Query Unit Tests (Slice ML-13)

Tests:
  - H1: Entity change history across snapshots
  - H2: Earliest issue origin discovery
  - H3: Risk evolution over time
"""

import pytest
from archon.pipeline.architecture.models import (
    ArchitectureAnalysisResult,
    ArchitectureCycle,
    ArchitectureViolation,
)
from archon.pipeline.evolution.models import (
    EvolutionAnalysisResult,
    SnapshotDiffResult,
    EntityDiff,
    ChangeType,
    ChangeRiskFact,
    RiskLevel,
)
from archon.pipeline.query.history import ArchitectureHistoryService


def test_entity_history_query():
    diff = SnapshotDiffResult(
        repository_id="r1",
        baseline_snapshot_id="s1",
        target_snapshot_id="s2",
        entity_diffs={
            "OrderService": EntityDiff(
                qualified_name="OrderService",
                entity_kind="Class",
                change_type=ChangeType.MODIFIED,
                field_changes={"architecture_role": ("service", "repository")},
            )
        },
    )
    evo_res = EvolutionAnalysisResult(
        repository_id="r1",
        baseline_snapshot_id="s1",
        target_snapshot_id="s2",
        diff=diff,
    )

    history_svc = ArchitectureHistoryService("r1")
    history, evidence, explanation = history_svc.get_entity_history("OrderService", evo_res)

    assert len(history) == 1
    assert any("MODIFIED" in h.description for h in history)
    assert any("architecture_role" in r for r in explanation.detailed_reasons)


def test_find_issue_origin():
    """Chronologically pinpoints first appearance of an issue"""
    arch1 = ArchitectureAnalysisResult(cycles=[])
    arch2 = ArchitectureAnalysisResult(cycles=[
        ArchitectureCycle("cycle:A->B", ["A", "B"], ["CALLS"], "medium", "r1", "s2", ""),
    ])
    arch3 = ArchitectureAnalysisResult(cycles=[
        ArchitectureCycle("cycle:A->B", ["A", "B"], ["CALLS"], "medium", "r1", "s3", ""),
    ])

    history_svc = ArchitectureHistoryService("r1")
    origin_snap, history, _, explanation = history_svc.find_issue_origin(
        issue_type="cycle",
        issue_key="cycle:A->B",
        snapshot_history=[("s1", arch1), ("s2", arch2), ("s3", arch3)],
    )

    assert origin_snap == "s2"
    assert "first appeared in snapshot 's2'" in explanation.summary
