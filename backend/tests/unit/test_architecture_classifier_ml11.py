"""
Architecture Classifier Unit Tests (Slice ML-11)

Tests:
  - Exact role classification via framework annotations (Spring @RestController, @Service, @Repository, ASP.NET [ApiController])
  - Inferred role classification via structural graph topology (HANDLED_BY, DEPENDS_ON)
  - Zero speculation guarantee: Naming alone never produces an exact classification
  - Role to layer mapping
  - Unknown role fallback
"""

import pytest
from archon.pipeline.parsers.java.parser import JavaParser
from archon.pipeline.parsers.csharp.parser import CSharpParser
from archon.pipeline.parsers.python.parser import PythonParser
from archon.pipeline.parsers.typescript.parser import TypeScriptParser
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import ArchitectureRole, ArchitectureLayer
from archon.pipeline.architecture.classifier import ArchitectureClassifier


def test_exact_controller_classification_spring():
    """Spring @RestController produces exact controller classification"""
    src = """\
package com.example.demo;

import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    public void getOrder() {}
}
"""
    p = JavaParser()
    pf = p.parse_file("OrderController.java", src)
    
    classifier = ArchitectureClassifier("repo-1", "snap-1")
    facts = classifier.classify_repository([pf], [], file_contents={"OrderController.java": src})
    
    fact = next((f for f in facts.values() if "OrderController" in f.qualified_name), None)
    assert fact is not None
    assert fact.architecture_role == ArchitectureRole.CONTROLLER
    assert fact.layer == ArchitectureLayer.PRESENTATION
    assert fact.resolution == "exact"
    assert fact.evidence_type == "framework_controller_annotation"


def test_exact_controller_classification_aspnet():
    """ASP.NET [ApiController] produces exact controller classification"""
    src = """\
namespace MyApp.Controllers
{
    [ApiController]
    public class OrderController : ControllerBase
    {
        public void Get() {}
    }
}
"""
    p = CSharpParser()
    pf = p.parse_file("OrderController.cs", src)
    
    classifier = ArchitectureClassifier("repo-1", "snap-1")
    facts = classifier.classify_repository([pf], [], file_contents={"OrderController.cs": src})
    
    fact = next((f for f in facts.values() if "OrderController" in f.qualified_name), None)
    assert fact is not None
    assert fact.architecture_role == ArchitectureRole.CONTROLLER
    assert fact.layer == ArchitectureLayer.PRESENTATION
    assert fact.resolution == "exact"


def test_exact_service_classification_spring():
    """Spring @Service produces exact service classification"""
    src = """\
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    public void charge() {}
}
"""
    p = JavaParser()
    pf = p.parse_file("PaymentService.java", src)
    
    classifier = ArchitectureClassifier("repo-1", "snap-1")
    facts = classifier.classify_repository([pf], [], file_contents={"PaymentService.java": src})
    
    fact = next((f for f in facts.values() if "PaymentService" in f.qualified_name), None)
    assert fact is not None
    assert fact.architecture_role == ArchitectureRole.SERVICE
    assert fact.layer == ArchitectureLayer.APPLICATION
    assert fact.resolution == "exact"


def test_exact_repository_classification_spring():
    """Spring @Repository produces exact repository classification"""
    src = """\
package com.example.demo;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    public void find() {}
}
"""
    p = JavaParser()
    pf = p.parse_file("OrderRepository.java", src)
    
    classifier = ArchitectureClassifier("repo-1", "snap-1")
    facts = classifier.classify_repository([pf], [], file_contents={"OrderRepository.java": src})
    
    fact = next((f for f in facts.values() if "OrderRepository" in f.qualified_name), None)
    assert fact is not None
    assert fact.architecture_role == ArchitectureRole.REPOSITORY
    assert fact.layer == ArchitectureLayer.INFRASTRUCTURE
    assert fact.resolution == "exact"


def test_naming_alone_never_produces_exact_service():
    """Class named 'TotallyRandomService' without annotations or structural wiring is UNKNOWN"""
    src = """\
class TotallyRandomService:
    def do_something(self):
        pass
"""
    p = PythonParser()
    pf = p.parse_file("random.py", src)
    
    classifier = ArchitectureClassifier("repo-1", "snap-1")
    facts = classifier.classify_repository([pf], [], file_contents={"random.py": src})
    
    fact = next((f for f in facts.values() if "TotallyRandomService" in f.qualified_name), None)
    assert fact is not None
    # Must NOT guess service exact purely from name
    assert fact.architecture_role == ArchitectureRole.UNKNOWN
    assert fact.resolution == "unresolved"


def test_inferred_service_from_dependency_layer_pattern():
    """Class called by Controller and calling downstream dependencies is classified as INFERRED service"""
    src_ctrl = """\
class OrderController:
    def checkout(self): pass
"""
    src_svc = """\
class OrderService:
    def process(self): pass
"""
    p = PythonParser()
    pf1 = p.parse_file("ctrl.py", src_ctrl)
    pf2 = p.parse_file("svc.py", src_svc)
    
    ctrl_qname = pf1.classes[0].qualified_name
    svc_qname = pf2.classes[0].qualified_name
    
    # Structural facts: OrderController is endpoint handler, DEPENDS_ON OrderService, OrderService DEPENDS_ON Repo
    resolved = [
        ResolutionResult(
            source_id="endpoint:POST:/orders",
            target_id=f"{ctrl_qname}.checkout",
            relationship="HANDLED_BY",
            resolution="exact",
            evidence_type="static_route",
            reason=""
        ),
        ResolutionResult(
            source_id=ctrl_qname,
            target_id=svc_qname,
            relationship="DEPENDS_ON",
            resolution="exact",
            evidence_type="constructor_type_annotation",
            reason=""
        ),
        ResolutionResult(
            source_id=svc_qname,
            target_id="repo.OrderRepository",
            relationship="DEPENDS_ON",
            resolution="exact",
            evidence_type="constructor_type_annotation",
            reason=""
        ),
    ]
    
    classifier = ArchitectureClassifier("repo-1", "snap-1")
    facts = classifier.classify_repository([pf1, pf2], resolved, file_contents={"ctrl.py": src_ctrl, "svc.py": src_svc})
    
    svc_fact = facts.get(svc_qname)
    assert svc_fact is not None
    assert svc_fact.architecture_role == ArchitectureRole.SERVICE
    assert svc_fact.layer == ArchitectureLayer.APPLICATION
    assert svc_fact.resolution == "inferred"
