"""
TypeScript & TSX Language Parser — Production Implementation (ML-2)

This module implements the universal LanguageParser contract for TypeScript (.ts)
and TSX (.tsx) source files using tree-sitter AST parsing.

Architecture & Security:
  - 100% static AST parsing via tree-sitter (C-level bindings).
  - Absolutely NO code execution, NO eval/exec, NO npm/node invocations.
  - Language-specific knowledge (syntax, AST nodes, module naming) is strictly
    isolated within this module and does not leak to the shared pipeline.
"""
import bisect
import os
import re
from typing import List, Optional, Tuple, Set
import structlog
from tree_sitter import Language, Parser, Node
import tree_sitter_typescript as tst

from archon.pipeline.parsers.base import (
    LanguageParser, ParsedFile, ParsedClass, ParsedFunction,
    ParsedParameter, ParsedImport, ResolvedCall
)
from archon.pipeline.parsers.registry import registry

logger = structlog.get_logger(__name__)

# Initialize tree-sitter grammars
TS_LANGUAGE = Language(tst.language_typescript())
TSX_LANGUAGE = Language(tst.language_tsx())


def _derive_typescript_module_name(path: str) -> str:
    """
    Derive a TypeScript canonical module name from a relative file path.

    This is TypeScript-specific logic and lives HERE inside the parser.
    Normalizes path separators to forward slashes and removes TypeScript extensions.

    Examples:
        "src/services/payment.service.ts" -> "src/services/payment.service"
        "src\\components\\App.tsx"        -> "src/components/App"
        "types/index.d.ts"                -> "types/index"
        "index.ts"                        -> "index"
    """
    name = path.replace("\\", "/")
    if name.startswith("./"):
        name = name[2:]
    if name.startswith("/"):
        name = name[1:]

    for ext in (".d.ts", ".ts", ".tsx"):
        if name.endswith(ext):
            name = name[:-len(ext)]
            break

    return name


def _clean_docstring(raw: str) -> str:
    """Cleans raw JSDoc/block comments into plain text."""
    lines = raw.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("/**"):
            stripped = stripped[3:].strip()
        elif stripped.startswith("/*"):
            stripped = stripped[2:].strip()
        elif stripped.startswith("*"):
            stripped = stripped[1:].strip()
        elif stripped.startswith("//"):
            stripped = stripped[2:].strip()
        if stripped.endswith("*/"):
            stripped = stripped[:-2].strip()
        cleaned_lines.append(stripped)
    return "\n".join(l for l in cleaned_lines if l).strip()


def _get_preceding_docstring(start_byte: int, source_bytes: bytes) -> Optional[str]:
    """
    Finds a JSDoc or block comment immediately preceding a byte offset in source_bytes.
    Pure Python string slicing — 100% safe against C cursor crashes.
    """
    if start_byte <= 0:
        return None

    preceding_text = source_bytes[:start_byte].decode("utf-8", errors="replace")
    lines = preceding_text.splitlines()
    if not lines:
        return None

    comment_lines = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            if comment_lines:
                break
            continue
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*") or stripped.endswith("*/"):
            comment_lines.append(stripped)
        else:
            break

    if comment_lines:
        comment_lines.reverse()
        full_comment = "\n".join(comment_lines)
        cleaned = _clean_docstring(full_comment)
        return cleaned or None

    return None


class TypeScriptVisitor:
    """
    Traverses tree-sitter AST to extract language-neutral structural entities.
    """

    def __init__(self, module_name: str, source_bytes: bytes):
        self.module_name = module_name
        self.source_bytes = source_bytes
        self.classes: List[ParsedClass] = []
        self.functions: List[ParsedFunction] = []
        self.imports: List[ParsedImport] = []
        self.line_starts = [0]
        for idx, b in enumerate(source_bytes):
            if b == ord(b"\n"):
                self.line_starts.append(idx + 1)

    def _byte_to_line(self, byte_offset: int) -> int:
        """Fast, pure-Python conversion of byte offset to 1-indexed line number."""
        return bisect.bisect_right(self.line_starts, byte_offset)

    def _text(self, node: Node) -> str:
        """Helper to get UTF-8 text of a tree-sitter node."""
        return self.source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _get_qualified_name(self, name: str, parent_class: Optional[str] = None) -> str:
        if parent_class:
            return f"{self.module_name}.{parent_class}.{name}"
        return f"{self.module_name}.{name}"

    def _compute_cc(self, node: Node) -> int:
        """
        Computes cyclomatic complexity for a TypeScript AST node using TreeCursor.
        Base complexity is 1. Increments for control-flow branches.
        100% C-memory safe via tree_sitter.TreeCursor traversal.
        """
        cc = 1
        branch_types = {
            "if_statement", "for_statement", "for_in_statement",
            "while_statement", "do_statement", "catch_clause",
            "switch_case", "conditional_expression",
        }
        cursor = node.walk()
        reached_root = False

        while not reached_root:
            if cursor.node != node:
                n_type = cursor.node.type
                if n_type in branch_types:
                    cc += 1
                elif n_type == "binary_expression":
                    text = self.source_bytes[cursor.node.start_byte:cursor.node.end_byte]
                    if b"&&" in text or b"||" in text or b"??" in text:
                        cc += 1

            if cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                continue

            retracing = True
            while retracing:
                if not cursor.goto_parent() or cursor.node == node:
                    reached_root = True
                    retracing = False
                    break
                if cursor.goto_next_sibling():
                    retracing = False
                    break

        return cc

    def _compute_nesting_depth(self, node: Node) -> int:
        """
        Computes structural nesting depth using TreeCursor.
        100% C-memory safe via tree_sitter.TreeCursor traversal.
        """
        nesting_types = {
            "if_statement", "for_statement", "for_in_statement",
            "while_statement", "do_statement", "try_statement",
            "catch_clause", "switch_statement"
        }

        max_depth = 0
        current_depth = 0
        cursor = node.walk()
        reached_root = False

        while not reached_root:
            if cursor.node != node and cursor.node.type in nesting_types:
                current_depth += 1
                if current_depth > max_depth:
                    max_depth = current_depth

            if cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                continue

            retracing = True
            while retracing:
                if cursor.node != node and cursor.node.type in nesting_types:
                    current_depth = max(0, current_depth - 1)

                if not cursor.goto_parent() or cursor.node == node:
                    reached_root = True
                    retracing = False
                    break
                if cursor.goto_next_sibling():
                    retracing = False
                    break

        return max_depth

    def _extract_calls(self, node: Node, is_method: bool = False) -> List[ResolvedCall]:
        """
        Extracts call sites from an AST node using TreeCursor.
        100% C-memory safe via tree_sitter.TreeCursor traversal.
        """
        calls: List[ResolvedCall] = []
        cursor = node.walk()
        reached_root = False

        while not reached_root:
            n = cursor.node
            if n.type == "call_expression":
                fn_node = n.child_by_field_name("function")
                if fn_node:
                    if fn_node.type == "identifier":
                        calls.append(ResolvedCall(
                            raw_name=self._text(fn_node),
                            target_qualified_name=None,
                            resolution="inferred"
                        ))
                    elif fn_node.type == "member_expression":
                        obj_node = fn_node.child_by_field_name("object")
                        prop_node = fn_node.child_by_field_name("property")
                        if prop_node:
                            raw_name = self._text(prop_node)
                            if obj_node and self._text(obj_node) in ("this", "super"):
                                calls.append(ResolvedCall(
                                    raw_name=raw_name,
                                    target_qualified_name=None,
                                    resolution="inferred"
                                ))
                            else:
                                calls.append(ResolvedCall(
                                    raw_name=raw_name,
                                    target_qualified_name=None,
                                    resolution="unresolved"
                                ))
                    elif fn_node.type == "super":
                        calls.append(ResolvedCall(
                            raw_name="super",
                            target_qualified_name=None,
                            resolution="inferred"
                        ))
                    else:
                        raw_name = self._text(fn_node).split("(")[0].strip()
                        if raw_name:
                            calls.append(ResolvedCall(
                                raw_name=raw_name,
                                target_qualified_name=None,
                                resolution="unresolved"
                            ))

            if cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                continue

            retracing = True
            while retracing:
                if not cursor.goto_parent() or cursor.node == node:
                    reached_root = True
                    retracing = False
                    break
                if cursor.goto_next_sibling():
                    retracing = False
                    break

        return calls

    def _extract_parameters(self, params_node: Optional[Node]) -> List[ParsedParameter]:
        """Extracts parameters and type annotations from formal_parameters node."""
        parameters: List[ParsedParameter] = []
        if not params_node:
            return parameters

        for child in params_node.named_children:
            name = ""
            type_annot = None
            if child.type in ("required_parameter", "optional_parameter"):
                p_name_node = child.child_by_field_name("pattern") or child.child_by_field_name("name")
                if p_name_node:
                    name = self._text(p_name_node)
                else:
                    # Fallback to first identifier
                    for sub in child.named_children:
                        if sub.type == "identifier":
                            name = self._text(sub)
                            break

                type_node = child.child_by_field_name("type")
                if type_node:
                    type_annot = self._text(type_node).lstrip(":").strip()

            elif child.type == "rest_parameter":
                for sub in child.named_children:
                    if sub.type == "identifier":
                        name = "..." + self._text(sub)
                    elif sub.type == "type_annotation":
                        type_annot = self._text(sub).lstrip(":").strip()

            elif child.type == "identifier":
                name = self._text(child)

            if name:
                parameters.append(ParsedParameter(name=name, type_annotation=type_annot))

        return parameters

    def visit(self, root_node: Node):
        """Top-level AST traversal using indexed named_child(i) to eliminate list allocations."""
        for i in range(root_node.named_child_count):
            self._visit_top_level_node(root_node.named_child(i))

    def _visit_top_level_node(self, node: Node):
        if node.type == "import_statement":
            self._visit_import(node)
        elif node.type == "export_statement":
            self._visit_export(node)
        elif node.type == "class_declaration":
            self._visit_class(node)
        elif node.type in ("function_declaration", "generator_function_declaration"):
            self._visit_function_declaration(node)
        elif node.type in ("lexical_declaration", "variable_declaration"):
            self._visit_variable_declaration(node)
        # Note on Interfaces/Types/Enums (Phase 4):
        # We intentionally do NOT convert interfaces or type aliases into ParsedClass
        # to avoid fabricating architectural facts not supported by the universal contract.

    def _visit_import(self, node: Node):
        """Extracts static import statements."""
        source_node = node.child_by_field_name("source")
        if not source_node:
            return

        raw_source = self._text(source_node).strip("'\"`")

        import_clause = None
        for i in range(node.named_child_count):
            child = node.named_child(i)
            if child.type == "import_clause":
                import_clause = child
                break

        if not import_clause:
            # Side-effect import: `import './styles.css'`
            self.imports.append(ParsedImport(
                name="",
                alias=None,
                is_from_import=False,
                module=raw_source
            ))
            return

        # Check default import: `import React from 'react'`
        for child in import_clause.children:
            if child.type == "identifier":
                self.imports.append(ParsedImport(
                    name=self._text(child),
                    alias=None,
                    is_from_import=False,
                    module=raw_source
                ))
            elif child.type == "namespace_import":
                # `import * as utils from './utils'`
                for sub in child.named_children:
                    if sub.type == "identifier":
                        self.imports.append(ParsedImport(
                            name=self._text(sub),
                            alias=self._text(sub),
                            is_from_import=False,
                            module=raw_source
                        ))
            elif child.type == "named_imports":
                # `import { A, B as C } from './module'`
                for spec in child.named_children:
                    if spec.type == "import_specifier":
                        name_node = spec.child_by_field_name("name")
                        alias_node = spec.child_by_field_name("alias")
                        if name_node:
                            name_text = self._text(name_node)
                            alias_text = self._text(alias_node) if alias_node else None
                            self.imports.append(ParsedImport(
                                name=name_text,
                                alias=alias_text,
                                is_from_import=True,
                                module=raw_source
                            ))

    def _visit_export(self, node: Node):
        """Handles export declarations wrapping classes, functions, variables, and re-exports."""
        source_node = node.child_by_field_name("source")
        if source_node:
            raw_source = self._text(source_node).strip("'\"`")
            for child in node.named_children:
                if child.type == "export_clause":
                    for spec in child.named_children:
                        if spec.type == "export_specifier":
                            name_n = spec.child_by_field_name("name")
                            alias_n = spec.child_by_field_name("alias")
                            if name_n:
                                self.imports.append(ParsedImport(
                                    name=self._text(name_n),
                                    alias=self._text(alias_n) if alias_n else None,
                                    is_from_import=True,
                                    module=raw_source
                                ))
                elif child.type == "namespace_export":
                    for sub in child.named_children:
                        if sub.type == "identifier":
                            self.imports.append(ParsedImport(
                                name="*",
                                alias=self._text(sub),
                                is_from_import=True,
                                module=raw_source
                            ))
            return

        for child in node.named_children:
            if child.type == "class_declaration":
                self._visit_class(child, parent_start_byte=node.start_byte)
            elif child.type in ("function_declaration", "generator_function_declaration"):
                self._visit_function_declaration(child, parent_start_byte=node.start_byte)
            elif child.type in ("lexical_declaration", "variable_declaration"):
                self._visit_variable_declaration(child, parent_start_byte=node.start_byte)

    def _visit_class(self, node: Node, parent_start_byte: Optional[int] = None):
        """Extracts TypeScript class declarations and their methods."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        class_name = self._text(name_node)
        base_classes: List[str] = []

        # Heritage (extends Base)
        heritage_node = None
        for i in range(node.named_child_count):
            child = node.named_child(i)
            if child.type == "class_heritage":
                heritage_node = child
                break

        if heritage_node:
            for clause in heritage_node.named_children:
                if clause.type == "extends_clause":
                    for ext_target in clause.named_children:
                        if ext_target.type in ("identifier", "type_identifier", "nested_type_identifier"):
                            base_classes.append(self._text(ext_target))

        start_line = self._byte_to_line(node.start_byte)
        end_line = self._byte_to_line(node.end_byte)
        line_count = max(1, end_line - start_line + 1)
        docstring = _get_preceding_docstring(parent_start_byte or node.start_byte, self.source_bytes)

        # Methods
        methods: List[ParsedFunction] = []
        body_node = node.child_by_field_name("body")
        if body_node:
            for member in body_node.named_children:
                if member.type == "method_definition":
                    method = self._extract_method(member, class_name)
                    if method:
                        methods.append(method)

        parsed_class = ParsedClass(
            name=class_name,
            qualified_name=self._get_qualified_name(class_name),
            base_classes=base_classes,
            methods=methods,
            start_line=start_line,
            end_line=end_line,
            line_count=line_count,
            docstring=docstring
        )
        self.classes.append(parsed_class)

    def _extract_method(self, node: Node, class_name: str) -> Optional[ParsedFunction]:
        """Extracts a method inside a class body."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        method_name = self._text(name_node)
        params_node = node.child_by_field_name("parameters")
        parameters = self._extract_parameters(params_node)

        # Return annotation
        return_annot = None
        type_node = node.child_by_field_name("return_type") or node.child_by_field_name("type")
        if type_node:
            return_annot = self._text(type_node).lstrip(":").strip()

        body_node = node.child_by_field_name("body")
        is_async = b"async" in self.source_bytes[node.start_byte:body_node.start_byte] if body_node else False

        # Decorators
        decorators: List[str] = []
        for child in node.named_children:
            if child.type == "decorator":
                decorators.append(self._text(child).lstrip("@").strip())

        calls = self._extract_calls(body_node, is_method=True) if body_node else []

        start_line = self._byte_to_line(node.start_byte)
        end_line = self._byte_to_line(node.end_byte)
        line_count = max(1, end_line - start_line + 1)
        docstring = _get_preceding_docstring(node.start_byte, self.source_bytes)

        return ParsedFunction(
            name=method_name,
            qualified_name=self._get_qualified_name(method_name, parent_class=class_name),
            parameters=parameters,
            decorators=decorators,
            return_annotation=return_annot,
            is_method=True,
            is_async=is_async,
            cyclomatic_complexity=self._compute_cc(node),
            nesting_depth=self._compute_nesting_depth(node),
            start_line=start_line,
            end_line=end_line,
            line_count=line_count,
            docstring=docstring,
            calls=calls
        )

    def _visit_function_declaration(self, node: Node, parent_start_byte: Optional[int] = None):
        """Extracts named function and generator declarations at module level."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        func_name = self._text(name_node)
        params_node = node.child_by_field_name("parameters")
        parameters = self._extract_parameters(params_node)

        return_annot = None
        type_node = node.child_by_field_name("return_type") or node.child_by_field_name("type")
        if type_node:
            return_annot = self._text(type_node).lstrip(":").strip()

        body_node = node.child_by_field_name("body")
        is_async = b"async" in self.source_bytes[node.start_byte:body_node.start_byte] if body_node else False
        calls = self._extract_calls(body_node, is_method=False) if body_node else []

        start_line = self._byte_to_line(node.start_byte)
        end_line = self._byte_to_line(node.end_byte)
        line_count = max(1, end_line - start_line + 1)
        docstring = _get_preceding_docstring(parent_start_byte or node.start_byte, self.source_bytes)

        self.functions.append(ParsedFunction(
            name=func_name,
            qualified_name=self._get_qualified_name(func_name),
            parameters=parameters,
            decorators=[],
            return_annotation=return_annot,
            is_method=False,
            is_async=is_async,
            cyclomatic_complexity=self._compute_cc(node),
            nesting_depth=self._compute_nesting_depth(node),
            start_line=start_line,
            end_line=end_line,
            line_count=line_count,
            docstring=docstring,
            calls=calls
        ))

    def _visit_variable_declaration(self, node: Node, parent_start_byte: Optional[int] = None):
        """
        Extracts:
          1. CommonJS literal `require()` imports (e.g. `const fs = require('fs')`)
          2. Named arrow functions and function expressions (`const foo = () => {}`)
        """
        for declarator in node.named_children:
            if declarator.type != "variable_declarator":
                continue

            name_node = declarator.child_by_field_name("name")
            val_node = declarator.child_by_field_name("value")

            if not name_node or not val_node:
                continue

            # Check for CommonJS require(): `const fs = require('fs')`
            if val_node.type == "call_expression":
                fn_node = val_node.child_by_field_name("function")
                if fn_node and self._text(fn_node) == "require":
                    args_node = val_node.child_by_field_name("arguments")
                    if args_node and args_node.named_child_count == 1:
                        arg0 = args_node.named_children[0]
                        if arg0.type in ("string", "string_fragment"):
                            raw_mod = self._text(arg0).strip("'\"`")
                            if name_node.type == "identifier":
                                self.imports.append(ParsedImport(
                                    name=self._text(name_node),
                                    alias=None,
                                    is_from_import=False,
                                    module=raw_mod
                                ))
                            elif name_node.type == "object_pattern":
                                for prop in name_node.named_children:
                                    if prop.type == "shorthand_property_identifier_pattern":
                                        self.imports.append(ParsedImport(
                                            name=self._text(prop),
                                            alias=None,
                                            is_from_import=True,
                                            module=raw_mod
                                        ))
                                    elif prop.type == "pair_pattern":
                                        key_node = prop.child_by_field_name("key")
                                        val_pat = prop.child_by_field_name("value")
                                        if key_node and val_pat:
                                            self.imports.append(ParsedImport(
                                                name=self._text(key_node),
                                                alias=self._text(val_pat),
                                                is_from_import=True,
                                                module=raw_mod
                                            ))
                            continue

            if val_node.type in ("arrow_function", "function_expression", "generator_function"):
                func_name = self._text(name_node)
                params_node = val_node.child_by_field_name("parameters")
                parameters = self._extract_parameters(params_node)

                return_annot = None
                type_node = val_node.child_by_field_name("return_type") or val_node.child_by_field_name("type")
                if type_node:
                    return_annot = self._text(type_node).lstrip(":").strip()

                body_node = val_node.child_by_field_name("body")
                is_async = b"async" in self.source_bytes[val_node.start_byte:body_node.start_byte] if body_node else False
                calls = self._extract_calls(body_node, is_method=False) if body_node else []

                start_line = self._byte_to_line(node.start_byte)
                end_line = self._byte_to_line(node.end_byte)
                line_count = max(1, end_line - start_line + 1)
                docstring = _get_preceding_docstring(parent_start_byte or node.start_byte, self.source_bytes)

                self.functions.append(ParsedFunction(
                    name=func_name,
                    qualified_name=self._get_qualified_name(func_name),
                    parameters=parameters,
                    decorators=[],
                    return_annotation=return_annot,
                    is_method=False,
                    is_async=is_async,
                    cyclomatic_complexity=self._compute_cc(val_node),
                    nesting_depth=self._compute_nesting_depth(val_node),
                    start_line=start_line,
                    end_line=end_line,
                    line_count=line_count,
                    docstring=docstring,
                    calls=calls
                ))


class TypeScriptParser(LanguageParser):
    """
    Production-quality TypeScript and TSX Language Parser.

    Satisfies the universal LanguageParser contract for:
      - `.ts`  (parsed via TypeScript grammar)
      - `.tsx` (parsed via TSX grammar)
    """

    def __init__(self):
        self._ts_parser = Parser(TS_LANGUAGE)
        self._tsx_parser = Parser(TSX_LANGUAGE)

    @property
    def language(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> List[str]:
        return [".ts", ".tsx"]

    def parse_file(self, path: str, content: str) -> ParsedFile:
        """
        Parses TypeScript / TSX source code into a language-neutral ParsedFile.
        Guaranteed to never raise; catches all errors and populates parse_errors.
        """
        module_name = _derive_typescript_module_name(path)
        total_lines = len(content.splitlines()) if content else 0

        try:
            source_bytes = content.encode("utf-8", errors="replace")

            # Route grammar by file extension
            if path.endswith(".tsx"):
                parser = Parser(TSX_LANGUAGE)
            else:
                parser = Parser(TS_LANGUAGE)
            tree = parser.parse(source_bytes)

            root = tree.root_node

            # Check if root has severe syntax errors
            parse_errors: List[str] = []
            if root.has_error:
                # Tree-sitter performs error recovery, but we record the presence of errors
                logger.warning("typescript_parse_syntax_warning", path=path)

            visitor = TypeScriptVisitor(module_name, source_bytes)
            visitor.visit(root)

            # Module-level docstring (if first top-level child is comment)
            docstring = None
            if root.named_child_count > 0:
                first_c = root.named_child(0)
                if first_c.type == "comment":
                    comment_text = source_bytes[first_c.start_byte:first_c.end_byte].decode("utf-8", errors="replace")
                    docstring = _clean_docstring(comment_text) or None

            return ParsedFile(
                path=path,
                language=self.language,
                module_name=module_name,
                total_lines=total_lines,
                docstring=docstring,
                classes=visitor.classes,
                functions=visitor.functions,
                imports=visitor.imports,
                parse_errors=parse_errors
            )

        except Exception as e:
            logger.error("typescript_parse_error", path=path, error=str(e))
            return ParsedFile(
                path=path,
                language=self.language,
                module_name=module_name,
                total_lines=total_lines,
                docstring=None,
                classes=[],
                functions=[],
                imports=[],
                parse_errors=[f"ParseError: {e}"]
            )


# Auto-register into the global registry at import time
registry.register(TypeScriptParser())
