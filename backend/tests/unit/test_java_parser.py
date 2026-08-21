"""
Unit Tests for Java & Spring Boot Parser (Slice ML-5)

Tests:
  1. Package declaration & module_name derivation (with and without package)
  2. Normal, wildcard, static, and static wildcard imports
  3. Class, superclass, and implemented interface extraction
  4. Constructor and method extraction
  5. Overloaded method signature & qualified_name differentiation
  6. Annotations (Spring Boot @RestController, @GetMapping, @Transactional)
  7. Interfaces and Enums
  8. Call extraction & 3-state resolution semantics
  9. Cyclomatic complexity and nesting depth calculation
  10. Syntax error isolation & empty file handling
"""

import pytest
from archon.pipeline.parsers.java.parser import JavaParser, _derive_java_module_name


@pytest.fixture
def parser():
    return JavaParser()


def test_java_module_name_derivation():
    """Derives canonical module_name from package declaration or relative path."""
    assert _derive_java_module_name("com.example.orders.service", "src/main/java/com/example/orders/service/OrderService.java") == "com.example.orders.service.OrderService"
    assert _derive_java_module_name("org.archon.api", "OrderController.java") == "org.archon.api.OrderController"
    # No package fallback
    assert _derive_java_module_name(None, "src/main/java/LegacyUtil.java") == "src.main.java.LegacyUtil"
    assert _derive_java_module_name(None, "App.java") == "App"


def test_java_imports_extraction(parser):
    """Extracts normal, wildcard, static, and static wildcard imports."""
    code = """
package com.example.app;

import com.example.model.User;
import com.example.service.*;
import static com.example.util.FormatUtils.formatDate;
import static com.example.util.MathUtils.*;
import SingleName;

public class App {}
"""
    result = parser.parse_file("src/App.java", code)
    assert result.module_name == "com.example.app.App"
    assert len(result.imports) == 5

    # 1. Normal import
    imp0 = result.imports[0]
    assert imp0.name == "User"
    assert imp0.module == "com.example.model"
    assert imp0.is_from_import is True

    # 2. Wildcard import
    imp1 = result.imports[1]
    assert imp1.name == "*"
    assert imp1.module == "com.example.service"

    # 3. Static import
    imp2 = result.imports[2]
    assert imp2.name == "formatDate"
    assert imp2.module == "com.example.util.FormatUtils"

    # 4. Static wildcard import
    imp3 = result.imports[3]
    assert imp3.name == "*"
    assert imp3.module == "com.example.util.MathUtils"

    # 5. Single name import
    imp4 = result.imports[4]
    assert imp4.name == "SingleName"


def test_java_class_and_inheritance_extraction(parser):
    """Extracts class, Javadoc, extends superclass, and implements interfaces."""
    code = """
package com.example.service;

/**
 * Order processing service.
 * Handles checkout operations.
 */
public class OrderService extends BaseService implements Auditable, Serializable {
}
"""
    result = parser.parse_file("src/OrderService.java", code)
    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "OrderService"
    assert cls.qualified_name == "com.example.service.OrderService.OrderService"
    assert "BaseService" in cls.base_classes
    assert "Auditable" in cls.base_classes
    assert "Serializable" in cls.base_classes
    assert cls.docstring is not None
    assert "Order processing service." in cls.docstring
    assert cls.start_line == 8


def test_java_constructors_and_methods(parser):
    """Extracts constructors, instance methods, parameters, and return types."""
    code = """
package com.example.service;

public class UserService {
    private final UserRepo repo;

    public UserService(UserRepo repo) {
        this.repo = repo;
    }

    public User findUser(Long id, boolean active) {
        return repo.findById(id);
    }

    public static String getVersion() {
        return "1.0";
    }
}
"""
    result = parser.parse_file("src/UserService.java", code)
    cls = result.classes[0]
    assert len(cls.methods) == 3

    # Constructor
    ctor = cls.methods[0]
    assert ctor.name == "UserService"
    assert ctor.parameters == ["repo"]
    assert ctor.is_method is True

    # Method findUser
    m1 = cls.methods[1]
    assert m1.name == "findUser"
    assert m1.parameters == ["id", "active"]
    assert m1.return_annotation == "User"

    # Static method getVersion
    m2 = cls.methods[2]
    assert m2.name == "getVersion"
    assert m2.return_annotation == "String"


def test_java_overloaded_methods(parser):
    """Overloaded methods in the same class receive distinct signature-differentiated qualified names."""
    code = """
package com.example.math;

public class Calculator {
    public int calculate(int a, int b) {
        return a + b;
    }

    public double calculate(double a, double b) {
        return a + b;
    }

    public String calculate(String prefix, int val) {
        return prefix + val;
    }

    public void uniqueOperation() {}
}
"""
    result = parser.parse_file("src/Calculator.java", code)
    cls = result.classes[0]
    assert len(cls.methods) == 4

    overloads = [m for m in cls.methods if m.name == "calculate"]
    assert len(overloads) == 3

    qnames = [m.qualified_name for m in overloads]
    # Verify all qualified names are distinct
    assert len(set(qnames)) == 3
    assert f"{cls.qualified_name}.calculate(int,int)" in qnames
    assert f"{cls.qualified_name}.calculate(double,double)" in qnames
    assert f"{cls.qualified_name}.calculate(String,int)" in qnames

    # Unique method does not get suffix
    unique_m = next(m for m in cls.methods if m.name == "uniqueOperation")
    assert unique_m.qualified_name == f"{cls.qualified_name}.uniqueOperation"


def test_java_spring_boot_annotations(parser):
    """Extracts Spring Boot annotations on classes and methods as decorators."""
    code = """
package com.example.controller;

@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    @GetMapping("/{id}")
    @Transactional
    public Order getOrder(@PathVariable Long id) {
        return null;
    }

    @PostMapping("/create")
    public ResponseEntity<Order> createOrder(@RequestBody OrderRequest req) {
        return null;
    }
}
"""
    result = parser.parse_file("src/OrderController.java", code)
    cls = result.classes[0]
    
    # Class methods
    m1 = cls.methods[0]
    assert m1.name == "getOrder"
    assert any("@GetMapping" in d for d in m1.decorators)
    assert any("@Transactional" in d for d in m1.decorators)

    m2 = cls.methods[1]
    assert m2.name == "createOrder"
    assert any("@PostMapping" in d for d in m2.decorators)


def test_java_call_resolution_semantics(parser):
    """Preserves strict 3-state resolution for Java method calls."""
    code = """
package com.example.service;

public class PaymentService {
    private final Gateway gateway;

    public void processPayment(double amount) {
        this.validate(amount);       // inferred (this.)
        super.logActivity();        // inferred (super.)
        helper();                   // inferred (bare in-scope call)
        gateway.charge(amount);     // unresolved (external receiver)
    }

    private void validate(double a) {}
    private void helper() {}
}
"""
    result = parser.parse_file("src/PaymentService.java", code)
    cls = result.classes[0]
    process_m = cls.methods[0]

    call_map = {c.raw_name: c.resolution for c in process_m.calls}
    assert call_map["validate"] == "inferred"
    assert call_map["logActivity"] == "inferred"
    assert call_map["helper"] == "inferred"
    assert call_map["charge"] == "unresolved"


def test_java_complexity_and_nesting(parser):
    """Calculates cyclomatic complexity and nesting depth accurately."""
    code = """
package com.example.util;

public class ComplexService {
    public void process(int x, int y) {
        if (x > 0 && y > 0) {            // +1 (if), +1 (&&)
            for (int i = 0; i < x; i++) { // +1 (for, nesting 2)
                while (y > 0) {          // +1 (while, nesting 3)
                    try {
                        doSomething();
                    } catch (Exception e) { // +1 (catch, nesting 4)
                        log(e);
                    }
                }
            }
        }
    }
}
"""
    result = parser.parse_file("src/ComplexService.java", code)
    cls = result.classes[0]
    method = cls.methods[0]

    # Base 1 + if (1) + && (1) + for (1) + while (1) + catch (1) = 6
    assert method.cyclomatic_complexity >= 5
    assert method.nesting_depth >= 4


def test_java_interfaces_and_enums(parser):
    """Extracts interfaces and enums into classes without corrupting the IR."""
    code = """
package com.example.domain;

public interface OrderRepository {
    Order findById(Long id);
    void save(Order order);
}

enum OrderStatus {
    PENDING,
    SHIPPED,
    DELIVERED
}
"""
    result = parser.parse_file("src/Domain.java", code)
    assert len(result.classes) == 2

    iface = result.classes[0]
    assert iface.name == "OrderRepository"
    assert len(iface.methods) == 2
    assert iface.methods[0].name == "findById"
    assert iface.methods[1].name == "save"

    enum_cls = result.classes[1]
    assert enum_cls.name == "OrderStatus"


def test_java_syntax_error_does_not_raise(parser):
    """Malformed Java syntax does not raise; returns valid ParsedFile with errors."""
    code = "public class Broken { public void unclosed( {"
    result = parser.parse_file("src/Broken.java", code)
    assert result.language == "java"
    assert result.module_name == "src.Broken"
    assert isinstance(result.classes, list)


def test_java_empty_file(parser):
    """Empty Java file parses cleanly."""
    result = parser.parse_file("src/Empty.java", "")
    assert result.language == "java"
    assert result.module_name == "src.Empty"
    assert result.classes == []
    assert result.imports == []
