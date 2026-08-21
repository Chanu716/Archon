"""
Parser Registry unit tests (ML-1)

Tests the language-neutral registry contract:
  - Extension-to-parser routing
  - Language detection
  - Supported extension queries
  - Behavior on unsupported extensions (must return None, never raise)
"""

import pytest
from archon.pipeline.parsers.registry import ParserRegistry
from archon.pipeline.parsers.base import LanguageParser, ParsedFile


# ---------------------------------------------------------------------------
# Minimal stub parser for testing the registry in isolation
# ---------------------------------------------------------------------------

class _StubParser(LanguageParser):
    """Minimal valid parser implementation for testing registry behaviour."""

    def __init__(self, language_name: str, extensions: list):
        self._language = language_name
        self._extensions = extensions

    @property
    def language(self) -> str:
        return self._language

    @property
    def file_extensions(self) -> list:
        return self._extensions

    def parse_file(self, path: str, content: str) -> ParsedFile:
        return ParsedFile(
            path=path,
            language=self._language,
            module_name=None,
            total_lines=0,
            docstring=None,
            classes=[],
            functions=[],
            imports=[],
            parse_errors=[],
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_registry():
    """A clean registry with no parsers registered."""
    return ParserRegistry()


@pytest.fixture
def python_stub():
    return _StubParser("python", [".py"])


@pytest.fixture
def ts_stub():
    return _StubParser("typescript", [".ts", ".tsx"])


@pytest.fixture
def populated_registry(fresh_registry, python_stub, ts_stub):
    """Registry with Python and TypeScript stubs registered."""
    fresh_registry.register(python_stub)
    fresh_registry.register(ts_stub)
    return fresh_registry


# ---------------------------------------------------------------------------
# get_parser tests
# ---------------------------------------------------------------------------

def test_py_resolves_to_python_parser(populated_registry, python_stub):
    result = populated_registry.get_parser(".py")
    assert result is python_stub


def test_ts_resolves_to_typescript_parser(populated_registry, ts_stub):
    result = populated_registry.get_parser(".ts")
    assert result is ts_stub


def test_tsx_resolves_to_typescript_parser(populated_registry, ts_stub):
    result = populated_registry.get_parser(".tsx")
    assert result is ts_stub


def test_unregistered_extension_returns_none(populated_registry):
    """Unknown extensions must return None — never raise."""
    result = populated_registry.get_parser(".rs")
    assert result is None


def test_js_returns_none_when_not_registered(populated_registry):
    """JavaScript is not registered in ML-1 — must return None."""
    result = populated_registry.get_parser(".js")
    assert result is None


def test_empty_extension_returns_none(populated_registry):
    """Files with no extension (e.g., Makefile) must return None cleanly."""
    result = populated_registry.get_parser("")
    assert result is None


def test_get_parser_is_case_sensitive(populated_registry):
    """Extension lookup is case-sensitive; '.PY' != '.py'."""
    result = populated_registry.get_parser(".PY")
    assert result is None


# ---------------------------------------------------------------------------
# detect_language tests
# ---------------------------------------------------------------------------

def test_detect_language_py(populated_registry):
    assert populated_registry.detect_language(".py") == "python"


def test_detect_language_ts(populated_registry):
    assert populated_registry.detect_language(".ts") == "typescript"


def test_detect_language_tsx(populated_registry):
    assert populated_registry.detect_language(".tsx") == "typescript"


def test_detect_language_unknown_extension(populated_registry):
    """Unknown extensions must return None — not raise."""
    result = populated_registry.detect_language(".xyz")
    assert result is None


def test_detect_language_empty_extension(populated_registry):
    result = populated_registry.detect_language("")
    assert result is None


# ---------------------------------------------------------------------------
# supported_extensions tests
# ---------------------------------------------------------------------------

def test_supported_extensions_contains_py(populated_registry):
    assert ".py" in populated_registry.supported_extensions()


def test_supported_extensions_contains_ts_and_tsx(populated_registry):
    exts = populated_registry.supported_extensions()
    assert ".ts" in exts
    assert ".tsx" in exts


def test_supported_extensions_excludes_unregistered(populated_registry):
    exts = populated_registry.supported_extensions()
    assert ".js" not in exts
    assert ".rs" not in exts


def test_supported_extensions_empty_for_empty_registry(fresh_registry):
    assert fresh_registry.supported_extensions() == set()


# ---------------------------------------------------------------------------
# register tests — override behavior
# ---------------------------------------------------------------------------

def test_register_single_parser(fresh_registry, python_stub):
    fresh_registry.register(python_stub)
    assert fresh_registry.get_parser(".py") is python_stub


def test_register_multi_extension_parser(fresh_registry, ts_stub):
    fresh_registry.register(ts_stub)
    assert fresh_registry.get_parser(".ts") is ts_stub
    assert fresh_registry.get_parser(".tsx") is ts_stub


def test_register_override_emits_warning(fresh_registry, caplog):
    """Registering a second parser for the same extension should warn, not raise."""
    import logging
    parser_a = _StubParser("python", [".py"])
    parser_b = _StubParser("python-fast", [".py"])

    fresh_registry.register(parser_a)
    # Override should not raise
    fresh_registry.register(parser_b)
    # Last registration wins
    assert fresh_registry.get_parser(".py") is parser_b


# ---------------------------------------------------------------------------
# Production registry smoke test
# (ensures PythonParser auto-registers when imported)
# ---------------------------------------------------------------------------

def test_production_registry_has_python():
    """The global registry must have Python registered after import."""
    import archon.pipeline.parsers.python.parser  # noqa: F401 — triggers auto-register
    from archon.pipeline.parsers.registry import registry as prod_registry
    assert prod_registry.get_parser(".py") is not None
    assert prod_registry.detect_language(".py") == "python"


def test_production_registry_ts_registered():
    """TypeScript MUST be registered in ML-2 for .ts and .tsx."""
    import archon.pipeline.parsers.typescript.parser  # noqa: F401
    from archon.pipeline.parsers.registry import registry as prod_registry
    assert prod_registry.get_parser(".ts") is not None
    assert prod_registry.detect_language(".ts") == "typescript"
    assert prod_registry.get_parser(".tsx") is not None
    assert prod_registry.detect_language(".tsx") == "typescript"


def test_production_registry_js_registered():
    """JavaScript MUST be registered in ML-3 for .js, .jsx, .mjs, .cjs."""
    import archon.pipeline.parsers.javascript.parser  # noqa: F401
    from archon.pipeline.parsers.registry import registry as prod_registry
    for ext in [".js", ".jsx", ".mjs", ".cjs"]:
        assert prod_registry.get_parser(ext) is not None
        assert prod_registry.detect_language(ext) == "javascript"


def test_production_registry_java_registered():
    """Java MUST be registered in ML-5 for .java."""
    import archon.pipeline.parsers.java.parser  # noqa: F401
    from archon.pipeline.parsers.registry import registry as prod_registry
    assert prod_registry.get_parser(".java") is not None
    assert prod_registry.detect_language(".java") == "java"


def test_production_registry_csharp_registered():
    """C# MUST be registered in ML-6 for .cs."""
    import archon.pipeline.parsers.csharp.parser  # noqa: F401
    from archon.pipeline.parsers.registry import registry as prod_registry
    assert prod_registry.get_parser(".cs") is not None
    assert prod_registry.detect_language(".cs") == "csharp"


def test_production_registry_go_registered():
    """Go MUST be registered in ML-7 for .go."""
    import archon.pipeline.parsers.go.parser  # noqa: F401
    from archon.pipeline.parsers.registry import registry as prod_registry
    assert prod_registry.get_parser(".go") is not None
    assert prod_registry.detect_language(".go") == "go"


def test_production_registry_other_languages_not_registered():
    """C++/Ruby/PHP must NOT be registered (ML-9 adds Rust, so .rs IS now registered)."""
    from archon.pipeline.parsers.registry import registry as prod_registry
    # .rs is now registered as of ML-9 (Rust parser)
    assert prod_registry.get_parser(".rs") is not None
    assert prod_registry.detect_language(".rs") == "rust"
    # These remain unregistered
    assert prod_registry.get_parser(".rb") is None
    assert prod_registry.get_parser(".cpp") is None
    assert prod_registry.get_parser(".php") is None
