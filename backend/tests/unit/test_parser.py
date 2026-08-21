"""
Parser unit tests — Python reference implementation + ML-1 contract assertions.

ML-1 contract requirements tested here:
  1. ParsedFile.module_name must be populated by the parser
  2. ParsedClass.start_line must be set
  3. ParsedFunction.start_line must be set
  4. All ML-1 assertions are additive — the original v1 assertions are preserved
"""

import pytest
from archon.pipeline.parsers.python.parser import PythonParser

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def parsed():
    """Parse a representative module once and return the result."""
    parser = PythonParser()
    code = '''\
"""Module docstring"""
import os
from collections import defaultdict

class Processor:
    """Class docstring"""
    def __init__(self):
        self.data = []
        
    def process(self):
        """Method docstring"""
        self.helper()
        os.path.join('a', 'b')
        unresolved_call()

def module_func():
    Processor().process()
'''
    return parser.parse_file("test_module.py", code)


# ---------------------------------------------------------------------------
# Original v1 contract assertions (preserved, unmodified)
# ---------------------------------------------------------------------------

def test_python_parser_extraction(parsed):
    assert parsed.language == "python"
    assert parsed.docstring == "Module docstring"
    assert len(parsed.imports) == 2

    assert len(parsed.classes) == 1
    cls = parsed.classes[0]
    assert cls.name == "Processor"
    assert cls.docstring == "Class docstring"
    assert len(cls.methods) == 2

    method = cls.methods[1]
    assert method.name == "process"
    assert method.docstring == "Method docstring"

    # Check calls in method
    call_names = {c.raw_name: c.resolution for c in method.calls}
    assert call_names["helper"] == "inferred"         # self.helper
    assert call_names["join"] == "unresolved"          # os.path.join
    assert call_names["unresolved_call"] == "inferred" # bare name => inferred

    assert len(parsed.functions) == 1
    func = parsed.functions[0]
    assert func.name == "module_func"
    assert func.calls[0].raw_name == "process"
    assert func.calls[0].resolution == "unresolved"   # Processor().process => attribute on non-self


# ---------------------------------------------------------------------------
# ML-1: module_name assertions
# ---------------------------------------------------------------------------

def test_module_name_is_populated(parsed):
    """ParsedFile.module_name must be set by the parser — not None."""
    assert parsed.module_name is not None


def test_module_name_strips_py_extension():
    """Python module names must not contain the .py extension."""
    parser = PythonParser()
    result = parser.parse_file("archon/pipeline/parsers/base.py", "")
    assert result.module_name == "archon.pipeline.parsers.base"


def test_module_name_simple_file():
    """Single-file paths derive correct dotted name."""
    parser = PythonParser()
    result = parser.parse_file("main.py", "")
    assert result.module_name == "main"


def test_module_name_nested_path():
    """Deeply nested paths produce correct dotted module names."""
    parser = PythonParser()
    result = parser.parse_file("a/b/c/d.py", "")
    assert result.module_name == "a.b.c.d"


def test_module_name_windows_separators():
    """Windows backslash separators produce correct dotted module names."""
    parser = PythonParser()
    result = parser.parse_file("archon\\pipeline\\base.py", "")
    assert result.module_name == "archon.pipeline.base"


# ---------------------------------------------------------------------------
# ML-1: start_line assertions on entities
# ---------------------------------------------------------------------------

def test_class_has_start_line(parsed):
    """ParsedClass.start_line must be set (>= 1)."""
    cls = parsed.classes[0]
    assert cls.start_line >= 1, "start_line must be populated on ParsedClass"


def test_class_start_line_before_end_line(parsed):
    """start_line must be <= end_line for all classes."""
    for cls in parsed.classes:
        assert cls.start_line <= cls.end_line


def test_method_has_start_line(parsed):
    """ParsedFunction.start_line must be set on methods."""
    cls = parsed.classes[0]
    for method in cls.methods:
        assert method.start_line >= 1, f"start_line not set on method {method.name}"


def test_method_start_line_before_end_line(parsed):
    """start_line must be <= end_line for all methods."""
    for cls in parsed.classes:
        for method in cls.methods:
            assert method.start_line <= method.end_line


def test_function_has_start_line(parsed):
    """ParsedFunction.start_line must be set on module-level functions."""
    for func in parsed.functions:
        assert func.start_line >= 1, f"start_line not set on function {func.name}"


def test_function_start_line_before_end_line(parsed):
    """start_line must be <= end_line for all functions."""
    for func in parsed.functions:
        assert func.start_line <= func.end_line


def test_start_line_ordering():
    """Class start_line must come before its method start_lines."""
    parser = PythonParser()
    code = """\
class Foo:
    def bar(self):
        pass
"""
    result = parser.parse_file("foo.py", code)
    cls = result.classes[0]
    bar = cls.methods[0]
    assert cls.start_line < bar.start_line


# ---------------------------------------------------------------------------
# ML-1: language field
# ---------------------------------------------------------------------------

def test_language_field_is_python(parsed):
    """language field must be the canonical Python identifier."""
    assert parsed.language == "python"


# ---------------------------------------------------------------------------
# ML-1: parse_errors on syntax error — graceful, no raise
# ---------------------------------------------------------------------------

def test_syntax_error_does_not_raise():
    """parse_file must never raise — syntax errors go to parse_errors."""
    parser = PythonParser()
    result = parser.parse_file("broken.py", "def foo(: this is broken python {{{")
    assert len(result.parse_errors) > 0
    assert result.language == "python"
    assert result.classes == []
    assert result.functions == []


def test_syntax_error_result_has_module_name():
    """Even on parse failure, module_name must be populated."""
    parser = PythonParser()
    result = parser.parse_file("archon/broken.py", "def foo(: broken")
    assert result.module_name == "archon.broken"


# ---------------------------------------------------------------------------
# ML-1: resolution states preserved
# ---------------------------------------------------------------------------

def test_resolution_states_preserved(parsed):
    """All three resolution states must be representable."""
    all_calls = []
    for cls in parsed.classes:
        for method in cls.methods:
            all_calls.extend(method.calls)
    for func in parsed.functions:
        all_calls.extend(func.calls)

    resolutions = {c.resolution for c in all_calls}
    assert "inferred" in resolutions
    assert "unresolved" in resolutions
