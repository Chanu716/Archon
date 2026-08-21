"""
Architecture Intelligence Service Integration Tests (Slice ML-11)

Tests:
  - ArchitectureIntelligenceService full analysis pass
  - Idempotency (running analysis twice produces identical results)
  - Snapshot isolation (different snapshots do not cross-pollinate)
"""

import pytest
from archon.pipeline.parsers.python.parser import PythonParser
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import ArchitectureRole, ArchitectureLayer
from archon.pipeline.architecture.service import ArchitectureIntelligenceService


def test_architecture_service_full_run():
    src_ctrl = """\
class OrderController:
    def checkout(self): pass
"""
    src_svc = """\
class OrderService:
    def process(self): pass
"""
    src_repo = """\
class OrderRepository:
    def save(self): pass
"""
    p = PythonParser()
    pf1 = p.parse_file("ctrl.py", src_ctrl)
    pf2 = p.parse_file("svc.py", src_svc)
    pf3 = p.parse_file("repo.py", src_repo)

    ctrl_qname = pf1.classes[0].qualified_name
    svc_qname = pf2.classes[0].qualified_name
    repo_qname = pf3.classes[0].qualified_name

    resolved = [
        ResolutionResult(source_id="endpoint:POST:/orders", target_id=f"{ctrl_qname}.checkout", relationship="HANDLED_BY", resolution="exact", evidence_type="", reason=""),
        ResolutionResult(source_id=ctrl_qname, target_id=svc_qname, relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
        ResolutionResult(source_id=svc_qname, target_id=repo_qname, relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
    ]

    contents = {"ctrl.py": src_ctrl, "svc.py": src_svc, "repo.py": src_repo}
    service = ArchitectureIntelligenceService("repo-1", "snap-1")
    result = service.analyze([pf1, pf2, pf3], resolved, file_contents=contents)

    assert result.summary["total_nodes"] >= 3
    assert result.summary["controllers"] >= 1
    assert result.summary["services"] >= 1
    assert result.summary["repositories"] >= 1
    assert result.summary["cycles_count"] == 0


def test_idempotency_and_snapshot_isolation():
    p = PythonParser()
    src = "class AppService:\n    def run(self): pass\n"
    pf = p.parse_file("app.py", src)
    resolved = []
    contents = {"app.py": src}

    svc1 = ArchitectureIntelligenceService("repo-1", "snap-1")
    res1_a = svc1.analyze([pf], resolved, file_contents=contents)
    res1_b = svc1.analyze([pf], resolved, file_contents=contents)

    assert res1_a.summary == res1_b.summary

    svc2 = ArchitectureIntelligenceService("repo-2", "snap-2")
    res2 = svc2.analyze([pf], resolved, file_contents=contents)

    fact2 = next(f for f in res2.nodes.values() if "AppService" in f.qualified_name)
    fact1 = next(f for f in res1_a.nodes.values() if "AppService" in f.qualified_name)

    assert fact2.snapshot_id == "snap-2"
    assert fact1.snapshot_id == "snap-1"
