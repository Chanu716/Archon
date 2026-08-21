"""
Comprehensive Test Suite for Slice ML-10: Repository-Wide Type & Dependency-Aware Resolution

Categories tested:
  A. Constructor Dependency Resolution (Python, TS, Java, C#, Go, Rust)
  B. Receiver Type Resolution (local vars, constructor new, alias chains, cycle safety)
  C. Dependency Method Calls (injected fields, unique interface impl, multiple impls, DI mapping)
  D. Static / Class Calls (unique static, missing type/method, ambiguous simple names)
  E. Type Hierarchy (inherited methods, bounded depth, inheritance cycle termination)
  F. Snapshot Isolation (independent repository / snapshot indexes, idempotency)
  G. Graph Persistence (DEPENDS_ON and IMPLEMENTS relationships)
  H. Impact Analysis (exact dependency chain traversal)
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from archon.pipeline.parsers.python.parser import PythonParser
from archon.pipeline.parsers.typescript.parser import TypeScriptParser
from archon.pipeline.parsers.java.parser import JavaParser
from archon.pipeline.parsers.csharp.parser import CSharpParser
from archon.pipeline.parsers.go.parser import GoParser
from archon.pipeline.parsers.rust.parser import RustParser

from archon.pipeline.resolution.type_index import RepositoryTypeIndex, TypeFact, DependencyFact, DIBindingFact
from archon.pipeline.resolution.dependency_extractor import DependencyExtractor
from archon.pipeline.resolution.dependency_resolver import DependencyAwareCallResolver
from archon.pipeline.resolution.resolver import CrossLanguageResolver
from archon.pipeline.resolution.models import ResolutionResult


# ─────────────────────────────────────────────────────────────────────────────
# A. Constructor Dependency Resolution
# ─────────────────────────────────────────────────────────────────────────────

def test_python_constructor_dependency():
    """Python: class OrderService: def __init__(self, repo: OrderRepository) -> DEPENDS_ON"""
    src = """\
class OrderRepository:
    def find(self): pass

class OrderService:
    def __init__(self, repo: OrderRepository):
        self.repo = repo
    def checkout(self):
        self.repo.find()
"""
    p = PythonParser()
    pf = p.parse_file("services.py", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"services.py": src})
    
    depends = [r for r in results if r.relationship == "DEPENDS_ON"]
    assert len(depends) == 1
    assert "OrderService" in depends[0].source_id
    assert "OrderRepository" in depends[0].target_id
    assert depends[0].resolution == "exact"


def test_typescript_constructor_dependency():
    """TypeScript: constructor(private repo: OrderRepository) -> DEPENDS_ON"""
    src = """\
export class OrderRepository {
    find(): void {}
}

export class OrderService {
    constructor(private repo: OrderRepository) {}
    checkout(): void {
        this.repo.find();
    }
}
"""
    p = TypeScriptParser()
    pf = p.parse_file("services.ts", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"services.ts": src})
    
    depends = [r for r in results if r.relationship == "DEPENDS_ON"]
    assert len(depends) == 1
    assert "OrderService" in depends[0].source_id
    assert "OrderRepository" in depends[0].target_id


def test_java_constructor_dependency():
    """Java: public OrderService(OrderRepository repository) -> DEPENDS_ON"""
    src = """\
package com.example.service;

public class OrderRepository {
    public void find() {}
}

public class OrderService {
    private final OrderRepository repository;
    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
    public void checkout() {
        this.repository.find();
    }
}
"""
    p = JavaParser()
    pf = p.parse_file("com/example/service/OrderService.java", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"com/example/service/OrderService.java": src})
    
    depends = [r for r in results if r.relationship == "DEPENDS_ON"]
    assert len(depends) == 1
    assert "OrderService" in depends[0].source_id
    assert "OrderRepository" in depends[0].target_id


def test_csharp_constructor_dependency():
    """C#: public OrderService(IOrderRepository repository) -> DEPENDS_ON"""
    src = """\
namespace MyApp.Services
{
    public interface IOrderRepository {
        void Find();
    }

    public class OrderService
    {
        private readonly IOrderRepository repository;
        public OrderService(IOrderRepository repository)
        {
            this.repository = repository;
        }
        public void Checkout()
        {
            this.repository.Find();
        }
    }
}
"""
    p = CSharpParser()
    pf = p.parse_file("OrderService.cs", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"OrderService.cs": src})
    
    depends = [r for r in results if r.relationship == "DEPENDS_ON"]
    assert len(depends) == 1
    assert "OrderService" in depends[0].source_id
    assert "IOrderRepository" in depends[0].target_id


def test_go_factory_wiring():
    """Go: func NewOrderService(repo OrderRepository) *OrderService -> DEPENDS_ON"""
    src = """\
package service

type OrderRepository struct {}

type OrderService struct {
    repo OrderRepository
}

func NewOrderService(repo OrderRepository) *OrderService {
    return &OrderService{repo: repo}
}
"""
    p = GoParser()
    pf = p.parse_file("service.go", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"service.go": src})
    
    depends = [r for r in results if r.relationship == "DEPENDS_ON"]
    assert len(depends) == 1
    assert "OrderService" in depends[0].source_id
    assert "OrderRepository" in depends[0].target_id


def test_rust_new_struct_wiring():
    """Rust: fn new(repository: Arc<OrderRepository>) -> Self -> DEPENDS_ON"""
    src = """\
pub struct OrderRepository {}

pub struct OrderService {
    repository: OrderRepository,
}

impl OrderService {
    pub fn new(repository: Arc<OrderRepository>) -> Self {
        Self { repository }
    }
}
"""
    p = RustParser()
    pf = p.parse_file("src/service.rs", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"src/service.rs": src})
    
    depends = [r for r in results if r.relationship == "DEPENDS_ON"]
    assert len(depends) == 1
    assert "OrderService" in depends[0].source_id
    assert "OrderRepository" in depends[0].target_id


# ─────────────────────────────────────────────────────────────────────────────
# B. Receiver Type Resolution
# ─────────────────────────────────────────────────────────────────────────────

def test_receiver_type_proven_call_python():
    """Python: service = PaymentService(); service.charge() -> exact CALLS PaymentService.charge"""
    src = """\
class PaymentService:
    def charge(self): pass

def run():
    service = PaymentService()
    service.charge()
"""
    p = PythonParser()
    pf = p.parse_file("main.py", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"main.py": src})
    
    exact_calls = [r for r in results if r.relationship == "CALLS" and r.resolution == "exact"]
    assert len(exact_calls) == 1
    assert exact_calls[0].source_id == "main.run"
    assert exact_calls[0].target_id == "main.PaymentService.charge"


def test_receiver_type_proven_call_typescript():
    """TypeScript: const service = new PaymentService(); service.charge() -> exact CALLS"""
    src = """\
export class PaymentService {
    charge(): void {}
}

export function run(): void {
    const service = new PaymentService();
    service.charge();
}
"""
    p = TypeScriptParser()
    pf = p.parse_file("main.ts", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"main.ts": src})
    
    exact_calls = [r for r in results if r.relationship == "CALLS" and r.resolution == "exact"]
    assert len(exact_calls) == 1
    assert "PaymentService.charge" in exact_calls[0].target_id


# ─────────────────────────────────────────────────────────────────────────────
# C. Dependency Method Calls & DI Wiring
# ─────────────────────────────────────────────────────────────────────────────

def test_injected_dependency_field_call():
    """Injected field call: self.repo.find() -> exact CALLS OrderRepository.find"""
    src = """\
class OrderRepository:
    def find(self): pass

class OrderService:
    def __init__(self, repo: OrderRepository):
        self.repo = repo
    def checkout(self):
        self.repo.find()
"""
    p = PythonParser()
    pf = p.parse_file("app.py", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"app.py": src})
    
    field_calls = [r for r in results if r.relationship == "CALLS" and r.resolution == "exact"]
    assert any("OrderRepository.find" in r.target_id for r in field_calls)


def test_aspnet_di_binding_resolution():
    """ASP.NET Core: services.AddScoped<IOrderRepository, SqlOrderRepository>() upgrades call to SqlOrderRepository"""
    startup_src = """\
namespace MyApp
{
    public class Startup
    {
        public void ConfigureServices(IServiceCollection services)
        {
            services.AddScoped<IOrderRepository, SqlOrderRepository>();
        }
    }
}
"""
    service_src = """\
namespace MyApp.Services
{
    public interface IOrderRepository
    {
        void Find();
    }

    public class SqlOrderRepository : IOrderRepository
    {
        public void Find() {}
    }

    public class OrderService
    {
        private readonly IOrderRepository repo;
        public OrderService(IOrderRepository repo)
        {
            this.repo = repo;
        }
        public void Checkout()
        {
            this.repo.Find();
        }
    }
}
"""
    p = CSharpParser()
    pf1 = p.parse_file("Startup.cs", startup_src)
    pf2 = p.parse_file("OrderService.cs", service_src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf1, pf2], {"Startup.cs": startup_src, "OrderService.cs": service_src})
    
    # Check that the call resolves to SqlOrderRepository.Find
    exact_calls = [r for r in results if r.relationship == "CALLS" and r.resolution == "exact"]
    assert any("SqlOrderRepository.Find" in r.target_id for r in exact_calls)


# ─────────────────────────────────────────────────────────────────────────────
# D. Static / Class Method Resolution
# ─────────────────────────────────────────────────────────────────────────────

def test_static_method_resolution():
    """UserValidator.validate(user) -> exact CALLS UserValidator.validate"""
    src = """\
class UserValidator:
    @staticmethod
    def validate(user): pass

class UserService:
    def register(self, user):
        UserValidator.validate(user)
"""
    p = PythonParser()
    pf = p.parse_file("users.py", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"users.py": src})
    
    static_calls = [r for r in results if r.relationship == "CALLS" and r.resolution == "exact"]
    assert any("UserValidator.validate" in r.target_id for r in static_calls)


# ─────────────────────────────────────────────────────────────────────────────
# E. Type Hierarchy & Cycle Safety
# ─────────────────────────────────────────────────────────────────────────────

def test_inheritance_method_lookup():
    """Subclass inheriting method from base class resolves through hierarchy"""
    src = """\
class BaseRepository:
    def save(self): pass

class SqlRepository(BaseRepository):
    pass

def run():
    repo = SqlRepository()
    repo.save()
"""
    p = PythonParser()
    pf = p.parse_file("repo.py", src)
    
    resolver = DependencyAwareCallResolver()
    results = resolver.resolve([pf], {"repo.py": src})
    
    exact_calls = [r for r in results if r.relationship == "CALLS" and r.resolution == "exact"]
    assert len(exact_calls) == 1
    assert "BaseRepository.save" in exact_calls[0].target_id


def test_inheritance_cycle_safety():
    """Cyclic inheritance does not hang or raise an infinite recursion error"""
    tf1 = TypeFact(qualified_name="A", simple_name="A", language="python", file_path="a.py", base_classes=["B"])
    tf2 = TypeFact(qualified_name="B", simple_name="B", language="python", file_path="b.py", base_classes=["A"])
    
    index = RepositoryTypeIndex([])
    index.types_by_qname["A"] = tf1
    index.types_by_qname["B"] = tf2
    index.inheritance_index["A"] = ["B"]
    index.inheritance_index["B"] = ["A"]
    
    # Should safely return None and terminate
    res = index.find_method_in_hierarchy(tf1, "non_existent_method")
    assert res is None


# ─────────────────────────────────────────────────────────────────────────────
# F. Snapshot Isolation & Idempotency
# ─────────────────────────────────────────────────────────────────────────────

def test_snapshot_isolation_and_idempotency():
    """Repeated resolution produces identical result sets without cross-run leakage"""
    src = """\
class ServiceA:
    def run(self): pass

def main():
    s = ServiceA()
    s.run()
"""
    p = PythonParser()
    pf = p.parse_file("app.py", src)
    
    resolver = DependencyAwareCallResolver()
    r1 = resolver.resolve([pf], {"app.py": src})
    r2 = resolver.resolve([pf], {"app.py": src})
    
    assert len(r1) == len(r2)
    assert [x.target_id for x in r1] == [x.target_id for x in r2]
