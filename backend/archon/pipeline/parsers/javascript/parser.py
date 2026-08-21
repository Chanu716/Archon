"""
JavaScript & JSX Language Parser — Production Implementation (ML-3)

This module implements the universal LanguageParser contract for JavaScript (.js),
JSX (.jsx), ES Modules (.mjs), and CommonJS (.cjs) source files using tree-sitter AST parsing.

Architecture & Security:
  - 100% static AST parsing via tree-sitter (C-level bindings).
  - Absolutely NO code execution, NO eval/exec, NO Node.js/npm invocations.
  - Language-specific knowledge (syntax, AST nodes, module naming) is strictly
    isolated within this module and does not leak to the shared pipeline.
"""

import bisect
from typing import List, Optional, Tuple, Set
import structlog
from tree_sitter import Language, Parser, Node
import tree_sitter_javascript as js_lang

from archon.pipeline.parsers.base import (
    LanguageParser, ParsedFile, ParsedClass, ParsedFunction,
    ParsedParameter, ParsedImport, ResolvedCall
)
from archon.pipeline.parsers.registry import registry

logger = structlog.get_logger(__name__)

# Initialize tree-sitter JavaScript/JSX grammar
JS_LANGUAGE = Language(js_lang.language())


def _derive_javascript_module_name(path: str) -> str:
    """
    Derive a JavaScript canonical module name from a relative file path.

    This is JavaScript-specific logic and lives HERE inside the parser.
    Normalizes path separators to forward slashes and removes JavaScript extensions.

    Examples:
        "src/components/Button.jsx" -> "src/components/Button"
        "utils/math.js"             -> "utils/math"
        "lib/esm/index.mjs"         -> "lib/esm/index"
        "config/db.cjs"             -> "config/db"
        "index.js"                  -> "index"
        "src\\utils\\file.js"       -> "src/utils/file"
    """
    name = path.replace("\\", "/")
    if name.startswith("./"):
        name = name[2:]
    if name.startswith("/"):
        name = name[1:]

    if name.endswith(".jsx"):
        name = name[:-4]
    elif name.endswith(".mjs"):
        name = name[:-4]
    elif name.endswith(".cjs"):
        name = name[:-4]
    elif name.endswith(".js"):
        name = name[:-3]

    return name


def _clean_docstring(comment_text: str) -> str:
    """Extract clean text from JSDoc or block comments."""
    lines = comment_text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("/**"):
            stripped = stripped[3:].strip()
        elif stripped.startswith("/*"):
            stripped = stripped[2:].strip()
        if stripped.endswith("*/"):
            stripped = stripped[:-2].strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped.startswith("//"):
            stripped = stripped[2:].strip()
        cleaned_lines.append(stripped)
    return "\n".join(l for l in cleaned_lines if l).strip()


def _get_preceding_docstring(start_byte: int, source_bytes: bytes) -> Optional[str]:
    """
    Finds a JSDoc or block comment immediately preceding a position in source_bytes.
    Pure Python string slicing — 100% safe from C-level tree-sitter pointer crashes.
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


class JavaScriptVisitor:
    """
    Traverses tree-sitter JavaScript AST to extract language-neutral structural entities.
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
        Computes cyclomatic complexity for a JavaScript AST node using TreeCursor.
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
        """Extracts parameters from formal_parameters node."""
        parameters: List[ParsedParameter] = []
        if not params_node:
            return parameters

        for child in params_node.named_children:
            name = ""
            if child.type == "identifier":
                name = self._text(child)
            elif child.type == "assignment_pattern":
                left = child.child_by_field_name("left")
                if left:
                    name = self._text(left)
            elif child.type == "rest_pattern":
                for sub in child.named_children:
                    if sub.type == "identifier":
                        name = "..." + self._text(sub)
            elif child.type == "object_pattern":
                # Destructured parameter e.g. ({ a, b })
                name = self._text(child)
            elif child.type == "array_pattern":
                name = self._text(child)

            if name:
                parameters.append(ParsedParameter(name=name, type_annotation=None))

        return parameters

    def visit(self, root_node: Node):
        """Top-level AST traversal using indexed named_child(i) to eliminate list allocations."""
        for i in range(root_node.named_child_count):
            self._visit_top_level_node(root_node.named_child(i))

    def _visit_top_level_node(self, node: Node):
        if node.type == "import_statement":
            self._visit_es_import(node)
        elif node.type == "export_statement":
            self._visit_export(node)
        elif node.type == "class_declaration":
            self._visit_class(node)
        elif node.type in ("function_declaration", "generator_function_declaration"):
            self._visit_function_declaration(node)
        elif node.type in ("lexical_declaration", "variable_declaration"):
            self._visit_variable_declaration(node)
        elif node.type == "expression_statement":
            self._visit_expression_statement(node)

    def _visit_es_import(self, node: Node):
        """Extracts static ES Module import statements."""
        source_node = node.child_by_field_name("source")
        if not source_node:
            return

        raw_source = self._text(source_node).strip("'\"`")

        import_clause = None
        for child in node.children:
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
                # `import { foo, bar as baz } from './utils'`
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

    def _visit_expression_statement(self, node: Node):
        """Extracts standalone CommonJS require side-effect imports, e.g. require('./polyfill');"""
        for child in node.named_children:
            if child.type == "call_expression":
                fn_node = child.child_by_field_name("function")
                if fn_node and self._text(fn_node) == "require":
                    args_node = child.child_by_field_name("arguments")
                    if args_node and args_node.named_child_count == 1:
                        arg0 = args_node.named_children[0]
                        if arg0.type in ("string", "string_fragment"):
                            raw_mod = self._text(arg0).strip("'\"`")
                            self.imports.append(ParsedImport(
                                name="",
                                alias=None,
                                is_from_import=False,
                                module=raw_mod
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
        """Extracts JavaScript class declarations and their methods."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous class (e.g. `export default class {}`) - omit to avoid fake identities
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
                        if ext_target.type in ("identifier", "nested_type_identifier", "member_expression"):
                            base_classes.append(self._text(ext_target))
                elif clause.type in ("identifier", "member_expression"):
                    base_classes.append(self._text(clause))

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

        body_node = node.child_by_field_name("body")
        is_async = b"async" in self.source_bytes[node.start_byte:body_node.start_byte] if body_node else False

        # Decorators (if Babel/TC39 decorators present)
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
            return_annotation=None,
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
            return_annotation=None,
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
          3. Stable object literal methods (`const service = { process() {}, ... }`)
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
                            # Check single identifier: `const fs = require('fs')`
                            if name_node.type == "identifier":
                                self.imports.append(ParsedImport(
                                    name=self._text(name_node),
                                    alias=None,
                                    is_from_import=False,
                                    module=raw_mod
                                ))
                            elif name_node.type == "object_pattern":
                                # `const { join, resolve: resPath } = require('path')`
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

            # Check Arrow functions & Function expressions
            if val_node.type in ("arrow_function", "function_expression", "generator_function"):
                if name_node.type == "identifier":
                    func_name = self._text(name_node)
                    params_node = val_node.child_by_field_name("parameters")
                    parameters = self._extract_parameters(params_node)

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
                        return_annotation=None,
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

            # Check Object Literal methods: `const service = { process() {}, validate: function() {} }`
            elif val_node.type == "object" and name_node.type == "identifier":
                obj_name = self._text(name_node)
                for prop in val_node.named_children:
                    if prop.type == "method_definition":
                        p_name_node = prop.child_by_field_name("name")
                        if p_name_node:
                            p_name = self._text(p_name_node)
                            params_node = prop.child_by_field_name("parameters")
                            parameters = self._extract_parameters(params_node)
                            body_node = prop.child_by_field_name("body")
                            is_async = b"async" in self.source_bytes[prop.start_byte:body_node.start_byte] if body_node else False
                            calls = self._extract_calls(body_node, is_method=False) if body_node else []
                            start_line = self._byte_to_line(prop.start_byte)
                            end_line = self._byte_to_line(prop.end_byte)
                            line_count = max(1, end_line - start_line + 1)
                            docstring = _get_preceding_docstring(prop.start_byte, self.source_bytes)

                            self.functions.append(ParsedFunction(
                                name=f"{obj_name}.{p_name}",
                                qualified_name=self._get_qualified_name(f"{obj_name}.{p_name}"),
                                parameters=parameters,
                                decorators=[],
                                return_annotation=None,
                                is_method=False,
                                is_async=is_async,
                                cyclomatic_complexity=self._compute_cc(prop),
                                nesting_depth=self._compute_nesting_depth(prop),
                                start_line=start_line,
                                end_line=end_line,
                                line_count=line_count,
                                docstring=docstring,
                                calls=calls
                            ))
                    elif prop.type == "pair":
                        key_node = prop.child_by_field_name("key")
                        val_func = prop.child_by_field_name("value")
                        if key_node and val_func and val_func.type in ("arrow_function", "function_expression"):
                            p_name = self._text(key_node)
                            params_node = val_func.child_by_field_name("parameters")
                            parameters = self._extract_parameters(params_node)
                            body_node = val_func.child_by_field_name("body")
                            is_async = b"async" in self.source_bytes[val_func.start_byte:body_node.start_byte] if body_node else False
                            calls = self._extract_calls(body_node, is_method=False) if body_node else []
                            start_line = self._byte_to_line(prop.start_byte)
                            end_line = self._byte_to_line(prop.end_byte)
                            line_count = max(1, end_line - start_line + 1)
                            docstring = _get_preceding_docstring(prop.start_byte, self.source_bytes)

                            self.functions.append(ParsedFunction(
                                name=f"{obj_name}.{p_name}",
                                qualified_name=self._get_qualified_name(f"{obj_name}.{p_name}"),
                                parameters=parameters,
                                decorators=[],
                                return_annotation=None,
                                is_method=False,
                                is_async=is_async,
                                cyclomatic_complexity=self._compute_cc(val_func),
                                nesting_depth=self._compute_nesting_depth(val_func),
                                start_line=start_line,
                                end_line=end_line,
                                line_count=line_count,
                                docstring=docstring,
                                calls=calls
                            ))


class JavaScriptParser(LanguageParser):
    """
    Production-quality JavaScript and JSX Language Parser.

    Satisfies the universal LanguageParser contract for:
      - `.js`
      - `.jsx`
      - `.mjs`
      - `.cjs`
    """

    def __init__(self):
        self._parser = Parser(JS_LANGUAGE)

    @property
    def language(self) -> str:
        return "javascript"

    @property
    def file_extensions(self) -> List[str]:
        return [".js", ".jsx", ".mjs", ".cjs"]

    def parse_file(self, path: str, content: str) -> ParsedFile:
        """
        Parses JavaScript / JSX / ESM / CommonJS source code into a language-neutral ParsedFile.
        Guaranteed to never raise; catches all errors and populates parse_errors.
        """
        module_name = _derive_javascript_module_name(path)
        total_lines = len(content.splitlines()) if content else 0

        try:
            source_bytes = content.encode("utf-8", errors="replace")
            parser = Parser(JS_LANGUAGE)
            tree = parser.parse(source_bytes)
            root = tree.root_node

            parse_errors: List[str] = []
            if root.has_error:
                logger.warning("javascript_parse_syntax_warning", path=path)

            visitor = JavaScriptVisitor(module_name, source_bytes)
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
            logger.error("javascript_parse_error", path=path, error=str(e))
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
registry.register(JavaScriptParser())
