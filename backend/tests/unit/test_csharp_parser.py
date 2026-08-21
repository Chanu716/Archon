"""
Unit Tests for C# & .NET Parser (Slice ML-6)

Tests:
  1. File-scoped namespace, block namespace, and fallback module_name derivation
  2. Standard, alias, static, and global using imports
  3. Class, superclass, and implemented interface extraction
  4. Interfaces, records, structs, and enums
  5. Constructor and method extraction (instance, static, async, expression-bodied)
  6. Overloaded method signature & qualified_name differentiation
  7. ASP.NET Core controller and route attributes
  8. Call extraction & strict 3-state resolution semantics
  9. Cyclomatic complexity and nesting depth calculation
  10. XML documentation comment extraction
  11. Syntax error isolation & empty file handling
"""

import pytest
from archon.pipeline.parsers.csharp.parser import CSharpParser, _derive_csharp_module_name, _clean_xml_docstring


@pytest.fixture
def parser():
    return CSharpParser()


def test_csharp_module_name_derivation():
    """Derives canonical module_name from file-scoped or block namespace or relative path."""
    assert _derive_csharp_module_name("MyApp.Services", "src/Services/PaymentService.cs") == "MyApp.Services.PaymentService"
    assert _derive_csharp_module_name("Archon.Controllers", "UsersController.cs") == "Archon.Controllers.UsersController"
    # No namespace fallback
    assert _derive_csharp_module_name(None, "src/LegacyUtil.cs") == "src.LegacyUtil"
    assert _derive_csharp_module_name(None, "Program.cs") == "Program"


def test_csharp_xml_docstring_cleaner():
    """Strips XML tags and slashes from C# XML documentation comments."""
    xml_comment = """
    /// <summary>
    /// Handles user registration and validation.
    /// </summary>
    /// <param name="user">The user payload.</param>
    """
    cleaned = _clean_xml_docstring(xml_comment)
    assert cleaned is not None
    assert "Handles user registration and validation." in cleaned
    assert "The user payload." in cleaned
    assert "<summary>" not in cleaned


def test_csharp_using_imports_extraction(parser):
    """Extracts standard, alias, static, and global using directives."""
    code = """
namespace MyApp.App;

using System;
using System.Collections.Generic;
using Alias = MyApp.Services.PaymentService;
global using MyApp.Common;

public class App {}
"""
    result = parser.parse_file("src/App.cs", code)
    assert result.module_name == "MyApp.App.App"
    assert len(result.imports) == 4

    # 1. Single name using
    imp0 = result.imports[0]
    assert imp0.name == "System"
    assert imp0.module is None

    # 2. Namespace using
    imp1 = result.imports[1]
    assert imp1.name == "Generic"
    assert imp1.module == "System.Collections"
    assert imp1.is_from_import is True

    # 3. Alias using
    imp2 = result.imports[2]
    assert imp2.name == "PaymentService"
    assert imp2.alias == "Alias"
    assert imp2.module == "MyApp.Services"

    # 4. Global using
    imp3 = result.imports[3]
    assert imp3.name == "Common"
    assert imp3.module == "MyApp"


def test_csharp_file_scoped_vs_block_namespace(parser):
    """Supports both file-scoped namespace and block namespace declarations."""
    # File-scoped
    code1 = "namespace MyApp.Core; public class Engine {}"
    r1 = parser.parse_file("src/Engine.cs", code1)
    assert r1.module_name == "MyApp.Core.Engine"
    assert len(r1.classes) == 1
    assert r1.classes[0].qualified_name == "MyApp.Core.Engine.Engine"

    # Block namespace
    code2 = """
namespace MyApp.Core
{
    public class Battery {}
}
"""
    r2 = parser.parse_file("src/Battery.cs", code2)
    assert r2.module_name == "MyApp.Core.Battery"
    assert len(r2.classes) == 1
    assert r2.classes[0].qualified_name == "MyApp.Core.Battery.Battery"


def test_csharp_classes_inheritance_interfaces(parser):
    """Extracts classes, XML docstrings, superclasses, and implemented interfaces."""
    code = """
namespace MyApp.Services;

/// <summary>
/// Service for processing online checkouts.
/// </summary>
public class CheckoutService : BaseService, ICheckoutService, IDisposable
{
}
"""
    result = parser.parse_file("src/CheckoutService.cs", code)
    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "CheckoutService"
    assert cls.qualified_name == "MyApp.Services.CheckoutService.CheckoutService"
    assert "BaseService" in cls.base_classes
    assert "ICheckoutService" in cls.base_classes
    assert "IDisposable" in cls.base_classes
    assert cls.docstring is not None
    assert "Service for processing online checkouts." in cls.docstring


def test_csharp_interfaces_records_structs_enums(parser):
    """Extracts interfaces, records, structs, and enums honestly without corrupting the IR."""
    code = """
namespace MyApp.Domain;

public interface IUserRepository
{
    Task<User> GetByIdAsync(int id);
}

public record UserDto(string Name, string Email);

public struct Coordinates
{
    public double Latitude { get; set; }
    public double Longitude { get; set; }
}

public enum OrderStatus
{
    Pending,
    Shipped,
    Delivered
}
"""
    result = parser.parse_file("src/Domain.cs", code)
    assert len(result.classes) == 4

    names = [c.name for c in result.classes]
    assert "IUserRepository" in names
    assert "UserDto" in names
    assert "Coordinates" in names
    assert "OrderStatus" in names


def test_csharp_constructors_and_methods(parser):
    """Extracts constructors, async methods, and expression-bodied methods."""
    code = """
namespace MyApp.Services;

public class OrderService
{
    private readonly IRepo _repo;

    public OrderService(IRepo repo)
    {
        _repo = repo;
    }

    public async Task<Order> GetOrderAsync(int id)
    {
        return await _repo.FindAsync(id);
    }

    public int GetDouble(int x) => x * 2;

    public static string GetVersion() => "1.0";
}
"""
    result = parser.parse_file("src/OrderService.cs", code)
    cls = result.classes[0]
    assert len(cls.methods) == 4

    # Constructor
    ctor = cls.methods[0]
    assert ctor.name == "OrderService"
    assert ctor.parameters == ["repo"]
    assert ctor.is_method is True

    # Async method
    m_async = cls.methods[1]
    assert m_async.name == "GetOrderAsync"
    assert m_async.is_async is True
    assert m_async.parameters == ["id"]

    # Expression-bodied method
    m_expr = cls.methods[2]
    assert m_expr.name == "GetDouble"
    assert m_expr.parameters == ["x"]

    # Static method
    m_stat = cls.methods[3]
    assert m_stat.name == "GetVersion"


def test_csharp_overloaded_methods(parser):
    """Overloaded methods in the same class receive distinct signature-differentiated qualified names."""
    code = """
namespace MyApp.Math;

public class Calculator
{
    public int Add(int a, int b) => a + b;
    public double Add(double a, double b) => a + b;
    public string Add(string a, string b) => a + b;
    public int UniqueOperation() => 42;
}
"""
    result = parser.parse_file("src/Calculator.cs", code)
    cls = result.classes[0]
    assert len(cls.methods) == 4

    overloads = [m for m in cls.methods if m.name == "Add"]
    assert len(overloads) == 3

    qnames = [m.qualified_name for m in overloads]
    assert len(set(qnames)) == 3
    assert f"{cls.qualified_name}.Add(int,int)" in qnames
    assert f"{cls.qualified_name}.Add(double,double)" in qnames
    assert f"{cls.qualified_name}.Add(string,string)" in qnames

    unique_m = next(m for m in cls.methods if m.name == "UniqueOperation")
    assert unique_m.qualified_name == f"{cls.qualified_name}.UniqueOperation"


def test_csharp_call_resolution_semantics(parser):
    """Preserves strict 3-state resolution for C# method calls."""
    code = """
namespace MyApp.Services;

public class PaymentService
{
    private readonly IGateway _gateway;

    public void Process(int amount)
    {
        this.Validate(amount);     // inferred (this.)
        base.LogAudit();          // inferred (base.)
        LocalHelper();            // inferred (bare local call)
        _gateway.Charge(amount);  // unresolved (external receiver)
    }

    private void Validate(int a) {}
    private void LocalHelper() {}
}
"""
    result = parser.parse_file("src/PaymentService.cs", code)
    cls = result.classes[0]
    process_m = cls.methods[0]

    call_map = {c.raw_name: c.resolution for c in process_m.calls}
    assert call_map["Validate"] == "inferred"
    assert call_map["LogAudit"] == "inferred"
    assert call_map["LocalHelper"] == "inferred"
    assert call_map["Charge"] == "unresolved"


def test_csharp_complexity_and_nesting(parser):
    """Calculates cyclomatic complexity and nesting depth accurately."""
    code = """
namespace MyApp.Util;

public class Logic
{
    public void Execute(int x, int y)
    {
        if (x > 0 && y > 0)             // +1 (if), +1 (&&)
        {
            foreach (var item in items)  // +1 (foreach, nesting 2)
            {
                while (x < 10)           // +1 (while, nesting 3)
                {
                    try
                    {
                        var val = x ?? 0; // +1 (??)
                    }
                    catch (Exception ex) // +1 (catch, nesting 4)
                    {
                        Log(ex);
                    }
                }
            }
        }
    }
}
"""
    result = parser.parse_file("src/Logic.cs", code)
    cls = result.classes[0]
    method = cls.methods[0]

    assert method.cyclomatic_complexity >= 5
    assert method.nesting_depth >= 4


def test_csharp_syntax_error_does_not_raise(parser):
    """Malformed C# syntax does not raise; returns valid ParsedFile with errors."""
    code = "namespace Broken; public class Unclosed { public void Bad( {"
    result = parser.parse_file("src/Broken.cs", code)
    assert result.language == "csharp"
    assert result.module_name == "Broken.Broken"
    assert isinstance(result.classes, list)


def test_csharp_empty_file(parser):
    """Empty C# file parses cleanly."""
    result = parser.parse_file("src/Empty.cs", "")
    assert result.language == "csharp"
    assert result.module_name == "src.Empty"
    assert result.classes == []
    assert result.imports == []
