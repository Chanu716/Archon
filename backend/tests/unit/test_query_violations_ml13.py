"""
Architecture Violation Query Unit Tests (Slice ML-13)

Tests:
  - Querying violation explanations by rule type
  - Structured evidence generation
"""

import pytest
from archon.pipeline.architecture.models import ArchitectureViolation
from archon.pipeline.query.service import ArchitectureQueryService


def test_explain_violation_via_service():
    viol = ArchitectureViolation(
        source_qualified_name="Domain.Order",
        target_qualified_name="Infrastructure.SqlRepo",
        violation_type="reverse_dependency",
        severity="high",
        resolution="exact",
        evidence_type="resolved_dependency_path",
        message="Domain layer must not depend on Infrastructure",
        repository_id="r1",
        snapshot_id="s1",
        source_layer="domain",
        target_layer="infrastructure",
    )

    service = ArchitectureQueryService("r1", "s1")
    res = service.explain_violation(viol)

    assert res.explanation is not None
    assert "reverse_dependency" in res.explanation.summary
    assert res.data["violation_type"] == "reverse_dependency"
    assert len(res.evidence) == 1
