"""
Python Language Parser — Reference Implementation (ML-1)

This is the reference implementation of the LanguageParser contract defined
in `archon.pipeline.parsers.base`. All other language parsers must follow
the same contract, not this implementation.

Python-specific details that MUST NOT leak to consumers:
  - The `ast` module and its node types
  - Python module name derivation (path -> dotted name)
  - Python-specific concepts (decorators, `self`, etc.)
"""

import ast
from typing import List, Optional, Any
from archon.pipeline.parsers.base import (
    LanguageParser, ParsedFile, ParsedClass, ParsedFunction,
    ParsedParameter, ParsedImport, ResolvedCall
)
from archon.pipeline.parsers.registry import registry
import structlog

logger = structlog.get_logger(__name__)


def _derive_python_module_name(path: str) -> str:
    """
    Derive a Python-style dotted module name from a relative file path.

    This is Python-specific logic and lives HERE in the parser, NOT in
    the GraphBuilder or EmbeddingGenerator. Consumers must use
    `ParsedFile.module_name` instead of re-deriving this themselves.

    Examples:
        "archon/pipeline/parsers/base.py" -> "archon.pipeline.parsers.base"
        "main.py"                         -> "main"
    """
    # Strip .py extension, then convert path separators to dots
    name = path
    if name.endswith(".py"):
        name = name[:-3]
    name = name.replace("/", ".").replace("\\", ".")
    # Strip leading dot if path was relative with leading separator
    if name.startswith("."):
        name = name[1:]
    return name


class PythonVisitor(ast.NodeVisitor):
    """
    AST visitor that extracts structural facts from Python source.

    This class is an implementation detail of PythonParser. It must
    not be imported or used by any code outside this file.
    """

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.classes: List[ParsedClass] = []
        self.functions: List[ParsedFunction] = []
        self.imports: List[ParsedImport] = []

        self._current_class: Optional[str] = None
        self._current_function: Optional[ast.FunctionDef | ast.AsyncFunctionDef] = None
        self._calls_in_current_function: List[ResolvedCall] = []

    def _get_qualified_name(self, name: str) -> str:
        if self._current_class:
            return f"{self.module_name}.{self._current_class}.{name}"
        return f"{self.module_name}.{name}"

    def _compute_cc(self, node: ast.AST) -> int:
        """Computes cyclomatic complexity of an AST node."""
        cc = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While,
                                  ast.ExceptHandler, ast.With, ast.AsyncWith,
                                  ast.Assert, ast.IfExp, ast.Match)):
                cc += 1
            elif isinstance(child, ast.BoolOp):
                cc += len(child.values) - 1
        return cc

    def _compute_nesting_depth(self, node: ast.AST) -> int:
        """Computes the maximum structural nesting depth of an AST node."""
        nesting_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While,
                         ast.Try, ast.With, ast.AsyncWith, ast.Match,
                         ast.ExceptHandler)

        max_depth = 0
        for child in ast.iter_child_nodes(node):
            child_depth = self._compute_nesting_depth(child)
            if isinstance(child, nesting_nodes):
                child_depth += 1
            max_depth = max(max_depth, child_depth)

        return max_depth

    def _get_source_range(self, node: ast.AST) -> tuple[int, int, int]:
        """Returns (start_line, end_line, line_count) for an AST node."""
        start = getattr(node, 'lineno', 1)
        end = getattr(node, 'end_lineno', start)
        return start, end, end - start + 1

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(ParsedImport(
                name=alias.name,
                alias=alias.asname,
                is_from_import=False,
                module=None
            ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(ParsedImport(
                name=alias.name,
                alias=alias.asname,
                is_from_import=True,
                module=module
            ))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_class = self._current_class
        self._current_class = node.name

        base_classes = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_classes.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_classes.append(base.attr)

        start_line, end_line, line_count = self._get_source_range(node)

        parsed_class = ParsedClass(
            name=node.name,
            qualified_name=self._get_qualified_name(node.name),
            base_classes=base_classes,
            methods=[],
            start_line=start_line,    # ML-1: populated
            end_line=end_line,
            line_count=line_count,
            docstring=ast.get_docstring(node)
        )
        self.classes.append(parsed_class)

        self.generic_visit(node)
        self._current_class = prev_class

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool):
        prev_function = self._current_function
        prev_calls = self._calls_in_current_function

        self._current_function = node
        self._calls_in_current_function = []

        parameters = []
        for arg in node.args.args:
            annotation = None
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    annotation = arg.annotation.id
                elif isinstance(arg.annotation, ast.Attribute):
                    annotation = arg.annotation.attr
            parameters.append(ParsedParameter(name=arg.arg, type_annotation=annotation))

        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)

        # Visit body to collect calls
        self.generic_visit(node)

        start_line, end_line, line_count = self._get_source_range(node)

        parsed_func = ParsedFunction(
            name=node.name,
            qualified_name=self._get_qualified_name(node.name),
            parameters=parameters,
            decorators=decorators,
            return_annotation=None,  # Simplified for current slice
            is_method=self._current_class is not None,
            is_async=is_async,
            cyclomatic_complexity=self._compute_cc(node),
            nesting_depth=self._compute_nesting_depth(node),
            start_line=start_line,   # ML-1: populated
            end_line=end_line,
            line_count=line_count,
            docstring=ast.get_docstring(node),
            calls=self._calls_in_current_function
        )

        if self._current_class:
            self.classes[-1].methods.append(parsed_func)
        else:
            self.functions.append(parsed_func)

        self._current_function = prev_function
        self._calls_in_current_function = prev_calls

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function(node, is_async=True)

    def visit_Call(self, node: ast.Call):
        if self._current_function is not None:
            raw_name = ""
            if isinstance(node.func, ast.Name):
                raw_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                raw_name = node.func.attr

            if raw_name:
                resolution = "unresolved"
                if isinstance(node.func, ast.Name):
                    # Bare name — same scope, inferred
                    resolution = "inferred"
                elif isinstance(node.func, ast.Attribute):
                    # self.method() — inferred; other.method() — unresolved
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                        resolution = "inferred"
                    else:
                        resolution = "unresolved"

                self._calls_in_current_function.append(ResolvedCall(
                    raw_name=raw_name,
                    target_qualified_name=None,
                    resolution=resolution
                ))

        self.generic_visit(node)


class PythonParser(LanguageParser):
    """
    Python language parser — reference implementation of LanguageParser.

    Produces a fully-populated ParsedFile with:
      - module_name (ML-1): Python dotted module name derived from the file path
      - start_line (ML-1): set on all ParsedClass and ParsedFunction instances
      - All existing fields from the v1 contract
    """

    @property
    def language(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> List[str]:
        return [".py"]

    def parse_file(self, path: str, content: str) -> ParsedFile:
        # Compute the canonical module name here — this is Python-specific
        # logic that must NOT be duplicated in consumers.
        module_name = _derive_python_module_name(path)

        try:
            tree = ast.parse(content, filename=path)
            visitor = PythonVisitor(module_name)
            visitor.visit(tree)

            return ParsedFile(
                path=path,
                language=self.language,
                module_name=module_name,          # ML-1: populated
                total_lines=len(content.splitlines()),
                docstring=ast.get_docstring(tree),
                classes=visitor.classes,
                functions=visitor.functions,
                imports=visitor.imports,
                parse_errors=[]
            )
        except SyntaxError as e:
            logger.warning("parse_syntax_error", path=path, error=str(e))
            return ParsedFile(
                path=path,
                language=self.language,
                module_name=module_name,
                total_lines=len(content.splitlines()),
                docstring=None,
                classes=[],
                functions=[],
                imports=[],
                parse_errors=[f"SyntaxError: {e}"]
            )
        except Exception as e:
            logger.error("parse_error", path=path, error=str(e))
            return ParsedFile(
                path=path,
                language=self.language,
                module_name=module_name,
                total_lines=len(content.splitlines()),
                docstring=None,
                classes=[],
                functions=[],
                imports=[],
                parse_errors=[f"ParseError: {e}"]
            )


# Self-register into the global registry at import time.
# The orchestrator imports this module to trigger registration.
registry.register(PythonParser())
