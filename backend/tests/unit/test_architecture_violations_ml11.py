"""
Architecture Violations Unit Tests (Slice ML-11)

Tests:
  - Layer skip: Presentation -> Infrastructure when Application layer exists
  - Reverse dependency: Domain -> Presentation, Infrastructure -> Presentation
  - Boundary bypass: Concrete dependency when DI interface exists
  - Allowed boundaries do not trigger violations
"""

import pytest
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import ArchitectureNodeFact, ArchitectureRole, ArchitectureLayer, ArchitectureCycle
from archon.pipeline.architecture.violations import ArchitectureViolationAnalyzer


def test_layer_skip_violation():
    """Controller directly depending on Repository when Service layer exists triggers layer_skip"""
    nodes = {
        "OrderController": ArchitectureNodeFact("OrderController", "Class", ArchitectureRole.CONTROLLER, ArchitectureLayer.PRESENTATION, "exact", "", "", "r1", "s1"),
        "OrderService": ArchitectureNodeFact("OrderService", "Class", ArchitectureRole.SERVICE, ArchitectureLayer.APPLICATION, "exact", "", "", "r1", "s1"),
        "OrderRepository": ArchitectureNodeFact("OrderRepository", "Class", ArchitectureRole.REPOSITORY, ArchitectureLayer.INFRASTRUCTURE, "exact", "", "", "r1", "s1"),
    }
    
    facts = [
        # Controller directly skips service to depend on repository
        ResolutionResult(source_id="OrderController", target_id="OrderRepository", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
    ]
    
    analyzer = ArchitectureViolationAnalyzer("r1", "s1")
    violations = analyzer.analyze_violations(nodes, facts, [])
    
    skips = [v for v in violations if v.violation_type == "layer_skip"]
    assert len(skips) == 1
    assert skips[0].source_qualified_name == "OrderController"
    assert skips[0].target_qualified_name == "OrderRepository"
    assert skips[0].severity == "medium"


def test_reverse_dependency_violation():
    """Domain model depending on Controller triggers reverse_dependency"""
    nodes = {
        "OrderEntity": ArchitectureNodeFact("OrderEntity", "Class", ArchitectureRole.DOMAIN, ArchitectureLayer.DOMAIN, "exact", "", "", "r1", "s1"),
        "OrderController": ArchitectureNodeFact("OrderController", "Class", ArchitectureRole.CONTROLLER, ArchitectureLayer.PRESENTATION, "exact", "", "", "r1", "s1"),
    }
    
    facts = [
        ResolutionResult(source_id="OrderEntity", target_id="OrderController", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
    ]
    
    analyzer = ArchitectureViolationAnalyzer("r1", "s1")
    violations = analyzer.analyze_violations(nodes, facts, [])
    
    revs = [v for v in violations if v.violation_type == "reverse_dependency"]
    assert len(revs) == 1
    assert revs[0].severity == "high"


def test_boundary_bypass_violation():
    """Direct dependency on StripeGateway when IPaymentGateway DI binding exists triggers boundary_bypass"""
    nodes = {
        "OrderService": ArchitectureNodeFact("OrderService", "Class", ArchitectureRole.SERVICE, ArchitectureLayer.APPLICATION, "exact", "", "", "r1", "s1"),
        "StripeGateway": ArchitectureNodeFact("StripeGateway", "Class", ArchitectureRole.INFRASTRUCTURE, ArchitectureLayer.INFRASTRUCTURE, "exact", "", "", "r1", "s1"),
    }
    
    facts = [
        ResolutionResult(source_id="OrderService", target_id="StripeGateway", relationship="DEPENDS_ON", resolution="exact", evidence_type="", reason=""),
    ]
    
    di_bindings = {
        "IPaymentGateway": "StripeGateway"
    }
    
    analyzer = ArchitectureViolationAnalyzer("r1", "s1")
    violations = analyzer.analyze_violations(nodes, facts, [], di_bindings=di_bindings)
    
    bypasses = [v for v in violations if v.violation_type == "boundary_bypass"]
    assert len(bypasses) == 1
    assert bypasses[0].source_qualified_name == "OrderService"
    assert bypasses[0].target_qualified_name == "StripeGateway"
