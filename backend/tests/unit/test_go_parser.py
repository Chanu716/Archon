"""
Unit Tests for Go Parser (Slice ML-7)

Tests:
  1. Package clause & module_name derivation
  2. Doc comment cleaning (// and /* */)
  3. Single, factored, aliased, blank, and dot imports
  4. Struct types and embedded struct inheritance
  5. Interface types extraction
  6. Top-level functions
  7. Receiver methods attached to structs
  8. Receiver methods for external structs preserved in functions
  9. 3-state call resolution (bare/receiver -> inferred, external -> unresolved)
  10. Cyclomatic complexity and nesting depth calculation
  11. Syntax error isolation & empty file handling
"""

import pytest
from archon.pipeline.parsers.go.parser import GoParser, _derive_go_module_name, _clean_docstring


@pytest.fixture
def parser():
    return GoParser()


def test_go_module_name_derivation():
    """Derives canonical module_name from package declaration or relative path."""
    assert _derive_go_module_name("orders", "src/services/OrderService.go") == "orders.OrderService"
    assert _derive_go_module_name("main", "main.go") == "main.main"
    # No package fallback
    assert _derive_go_module_name(None, "src/util.go") == "src.util"
    assert _derive_go_module_name(None, "server.go") == "server"


def test_go_docstring_cleaner():
    """Cleans Go single-line and multi-line comments."""
    comment1 = """
    // OrderService handles order lifecycle.
    // It coordinates billing and shipping.
    """
    cleaned1 = _clean_docstring(comment1)
    assert cleaned1 is not None
    assert "OrderService handles order lifecycle." in cleaned1
    assert "//" not in cleaned1

    comment2 = """
    /*
     * Package math provides basic constants.
     */
    """
    cleaned2 = _clean_docstring(comment2)
    assert cleaned2 is not None
    assert "Package math provides basic constants." in cleaned2


def test_go_imports_extraction(parser):
    """Extracts single, factored, aliased, blank, and dot imports."""
    code = """
package main

import (
    "fmt"
    "net/http"
    u "github.com/example/util"
    _ "github.com/lib/pq"
    . "github.com/example/lib"
)

func main() {}
"""
    result = parser.parse_file("src/main.go", code)
    assert result.module_name == "main.main"
    assert len(result.imports) == 5

    # 1. Single name
    imp0 = result.imports[0]
    assert imp0.name == "fmt"
    assert imp0.module is None

    # 2. Path import
    imp1 = result.imports[1]
    assert imp1.name == "http"
    assert imp1.module == "net"
    assert imp1.is_from_import is True

    # 3. Aliased import
    imp2 = result.imports[2]
    assert imp2.name == "util"
    assert imp2.alias == "u"
    assert imp2.module == "github.com/example"

    # 4. Blank import
    imp3 = result.imports[3]
    assert imp3.name == "pq"
    assert imp3.alias == "_"

    # 5. Dot import
    imp4 = result.imports[4]
    assert imp4.name == "lib"
    assert imp4.alias == "."


def test_go_structs_and_embedded_fields(parser):
    """Extracts structs, docstrings, and embedded structs as base_classes."""
    code = """
package services

// OrderService handles order lifecycle.
type OrderService struct {
    BaseService
    *AuditLogger
    repo Repo
}
"""
    result = parser.parse_file("src/services/OrderService.go", code)
    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "OrderService"
    assert cls.qualified_name == "services.OrderService.OrderService"
    assert "BaseService" in cls.base_classes
    assert "AuditLogger" in cls.base_classes
    assert cls.docstring is not None
    assert "OrderService handles order lifecycle." in cls.docstring


def test_go_interfaces_extraction(parser):
    """Extracts Go interfaces into ParsedClass entities."""
    code = """
package domain

// UserRepository provides access to user records.
type UserRepository interface {
    FindById(id int) (*User, error)
    Save(u *User) error
}
"""
    result = parser.parse_file("src/domain/repo.go", code)
    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "UserRepository"
    assert cls.qualified_name == "domain.repo.UserRepository"
    assert cls.docstring is not None
    assert "UserRepository provides access to user records." in cls.docstring


def test_go_functions_and_receiver_methods(parser):
    """Extracts top-level functions and receiver methods attached to structs."""
    code = """
package services

type PaymentService struct {}

func NewPaymentService() *PaymentService {
    return &PaymentService{}
}

// ProcessPayment processes customer charge.
func (s *PaymentService) ProcessPayment(amount int) (bool, error) {
    return true, nil
}

func (s PaymentService) Validate(amount int) bool {
    return amount > 0
}
"""
    result = parser.parse_file("src/services/PaymentService.go", code)
    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "PaymentService"

    # Methods attached to PaymentService
    assert len(cls.methods) == 2
    m1 = cls.methods[0]
    assert m1.name == "ProcessPayment"
    assert m1.is_method is True
    assert m1.parameters == ["amount"]
    assert m1.qualified_name == "services.PaymentService.PaymentService.ProcessPayment"
    assert m1.docstring is not None

    m2 = cls.methods[1]
    assert m2.name == "Validate"
    assert m2.is_method is True

    # Top-level constructor function
    assert len(result.functions) == 1
    fn = result.functions[0]
    assert fn.name == "NewPaymentService"
    assert fn.is_method is False
    assert fn.qualified_name == "services.PaymentService.NewPaymentService"


def test_go_receiver_method_separate_file(parser):
    """Preserves receiver methods in functions when struct is in another file."""
    code = """
package services

func (s *OrderService) CalculateDiscount(pct float64) float64 {
    return 10.0
}
"""
    result = parser.parse_file("src/services/OrderService_ext.go", code)
    assert len(result.classes) == 0
    assert len(result.functions) == 1

    fn = result.functions[0]
    assert fn.name == "CalculateDiscount"
    assert fn.is_method is True
    assert fn.qualified_name == "services.OrderService_ext.OrderService.CalculateDiscount"


def test_go_call_resolution_semantics(parser):
    """Preserves strict 3-state resolution for Go function and method calls."""
    code = """
package services

type CheckoutService struct {
    gateway Gateway
}

func (s *CheckoutService) Checkout(id int) {
    s.validate(id)          // inferred (receiver method)
    localHelper()           // inferred (bare function call)
    s.gateway.Charge(id)    // unresolved (external receiver)
    fmt.Println(id)         // unresolved (external package)
}

func (s *CheckoutService) validate(id int) {}
func localHelper() {}
"""
    result = parser.parse_file("src/services/CheckoutService.go", code)
    cls = result.classes[0]
    method = cls.methods[0]

    call_map = {c.raw_name: c.resolution for c in method.calls}
    assert call_map["validate"] == "inferred"
    assert call_map["localHelper"] == "inferred"
    assert call_map["Charge"] == "unresolved"
    assert call_map["Println"] == "unresolved"


def test_go_complexity_and_nesting(parser):
    """Calculates cyclomatic complexity and nesting depth for Go control flow."""
    code = """
package util

func Process(x int, y int) int {
    if x > 0 && y > 0 {             // +1 (if), +1 (&&)
        for i := 0; i < x; i++ {    // +1 (for, nesting 2)
            switch i {              // nesting 3
            case 1:                 // +1 (case)
                return 1
            case 2:                 // +1 (case)
                return 2
            default:
                break
            }
        }
    }
    return 0
}
"""
    result = parser.parse_file("src/util.go", code)
    fn = result.functions[0]

    assert fn.cyclomatic_complexity >= 5
    assert fn.nesting_depth >= 3


def test_go_syntax_error_does_not_raise(parser):
    """Malformed Go syntax does not raise; returns valid ParsedFile with errors."""
    code = "package broken; func Bad( {"
    result = parser.parse_file("src/broken.go", code)
    assert result.language == "go"
    assert result.module_name == "broken.broken"
    assert isinstance(result.functions, list)


def test_go_empty_file(parser):
    """Empty Go file parses cleanly."""
    result = parser.parse_file("src/empty.go", "")
    assert result.language == "go"
    assert result.module_name == "src.empty"
    assert result.classes == []
    assert result.functions == []
    assert result.imports == []
