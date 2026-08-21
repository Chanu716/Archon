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


def _get_preceding_docstring(node: Node, source_bytes: bytes) -> Optional[str]:
    """Finds a JSDoc or block comment immediately preceding this AST node or its export wrapper."""
    prev = node.prev_sibling
    if prev and prev.type == "comment":
        comment_text = source_bytes[prev.start_byte:prev.end_byte].decode("utf-8", errors="replace")
        cleaned = _clean_docstring(comment_text)
        if cleaned:
            return cleaned

    # If wrapped in an export statement, check the export statement's preceding comment
    if node.parent and node.parent.type in ("export_statement", "export_default_declaration"):
        parent_prev = node.parent.prev_sibling
        if parent_prev and parent_prev.type == "comment":
            comment_text = source_bytes[parent_prev.start_byte:parent_prev.end_byte].decode("utf-8", errors="replace")
            cleaned = _clean_docstring(comment_text)
            if cleaned:
                return cleaned

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

    def _text(self, node: Node) -> str:
        """Helper to get UTF-8 text of a tree-sitter node."""
        return self.source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _get_qualified_name(self, name: str, parent_class: Optional[str] = None) -> str:
        if parent_class:
            return f"{self.module_name}.{parent_class}.{name}"
        return f"{self.module_name}.{name}"

    def _compute_cc(self, node: Node) -> int:
        """
        Computes cyclomatic complexity for a JavaScript AST node.
        Base complexity is 1. Increments for control-flow branches.
        """
        cc = 1
        branch_types = {
            "if_statement", "for_statement", "for_in_statement",
            "while_statement", "do_statement", "catch_clause",
            "switch_case", "conditional_expression",  # ternary ? :
        }

        def walk(n: Node):
            nonlocal cc
            if n.type in branch_types:
                cc += 1
            elif n.type == "binary_expression":
                op = n.child_by_field_name("operator")
                if op and self._text(op) in ("&&", "||", "??"):
                    cc += 1
            for child in n.children:
                walk(child)

        walk(node)
        return cc

    def _compute_nesting_depth(self, node: Node) -> int:
        """Computes structural nesting depth of control flow within an AST node."""
        nesting_types = {
            "if_statement", "for_statement", "for_in_statement",
            "while_statement", "do_statement", "try_statement",
            "catch_clause", "switch_statement"
        }

        max_depth = 0
        for child in node.children:
            child_depth = self._compute_nesting_depth(child)
            if child.type in nesting_types:
                child_depth += 1
            max_depth = max(max_depth, child_depth)

        return max_depth

    def _extract_calls(self, node: Node, is_method: bool = False) -> List[ResolvedCall]:
        """
        Extracts call sites from a function or method body.
        Preserves Archon's exact/inferred/unresolved resolution semantics:
          - bare function call (e.g. `calculateTotal()`) -> 'inferred' (local/module scope)
          - this.method() or super.method() -> 'inferred' (class instance method)
          - object.method() (e.g. `utils.log()`, `client.api.call()`) -> 'unresolved'
        """
        calls: List[ResolvedCall] = []

        def walk(n: Node):
            if n.type == "call_expression":
                fn_node = n.child_by_field_name("function")
                if fn_node:
                    if fn_node.type == "identifier":
                        # Bare name: inferred in scope
                        raw_name = self._text(fn_node)
                        calls.append(ResolvedCall(
                            raw_name=raw_name,
                            target_qualified_name=None,
                            resolution="inferred"
                        ))
                    elif fn_node.type == "member_expression":
                        obj_node = fn_node.child_by_field_name("object")
                        prop_node = fn_node.child_by_field_name("property")
                        if prop_node:
                            raw_name = self._text(prop_node)
                            if obj_node and self._text(obj_node) in ("this", "super"):
                                # Class method invocation on self
                                calls.append(ResolvedCall(
                                    raw_name=raw_name,
                                    target_qualified_name=None,
                                    resolution="inferred"
                                ))
                            else:
                                # External object invocation
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

            for child in n.children:
                walk(child)

        walk(node)
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
        """Top-level AST traversal."""
        for child in root_node.named_children:
            self._visit_top_level_node(child)

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
            for child in node.children:
                if child.type == "export_clause":
                    for spec in child.named_children:
                        if spec.type == "export_specifier":
                            name_n = spec.child_by_field_name("name")
                            alias_n = spec.child_by_field_name("alias")
                            if name_n:
                                name_text = self._text(name_n)
                                alias_text = self._text(alias_n) if alias_n else None
                                self.imports.append(ParsedImport(
                                    name=name_text,
                                    alias=alias_text,
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
            if any(c.type == "*" for c in node.children):
                self.imports.append(ParsedImport(
                    name="*",
                    alias=None,
                    is_from_import=True,
                    module=raw_source
                ))

        for child in node.named_children:
            if child.type == "class_declaration":
                self._visit_class(child)
            elif child.type in ("function_declaration", "generator_function_declaration"):
                self._visit_function_declaration(child)
            elif child.type in ("lexical_declaration", "variable_declaration"):
                self._visit_variable_declaration(child)

    def _visit_class(self, node: Node):
        """Extracts JavaScript class declarations and their methods."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous class (e.g. `export default class {}`) - omit to avoid fake identities
            return

        class_name = self._text(name_node)
        base_classes: List[str] = []

        # Heritage (extends Base)
        heritage_node = None
        for child in node.children:
            if child.type == "class_heritage":
                heritage_node = child
                break

        if heritage_node:
            for clause in heritage_node.children:
                if clause.type == "extends_clause":
                    for ext_target in clause.named_children:
                        if ext_target.type in ("identifier", "nested_type_identifier", "member_expression"):
                            base_classes.append(self._text(ext_target))
                elif clause.type in ("identifier", "member_expression"):
                    base_classes.append(self._text(clause))

        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = end_line - start_line + 1
        docstring = _get_preceding_docstring(node, self.source_bytes)

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

        is_async = any(child.type == "async" for child in node.children)

        # Decorators (if Babel/TC39 decorators present)
        decorators: List[str] = []
        for child in node.children:
            if child.type == "decorator":
                decorators.append(self._text(child).lstrip("@").strip())

        body_node = node.child_by_field_name("body")
        calls = self._extract_calls(body_node, is_method=True) if body_node else []

        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = end_line - start_line + 1
        docstring = _get_preceding_docstring(node, self.source_bytes)

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

    def _visit_function_declaration(self, node: Node):
        """Extracts named function and generator declarations at module level."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        func_name = self._text(name_node)
        params_node = node.child_by_field_name("parameters")
        parameters = self._extract_parameters(params_node)

        is_async = any(c.type == "async" for c in node.children)
        body_node = node.child_by_field_name("body")
        calls = self._extract_calls(body_node, is_method=False) if body_node else []

        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = end_line - start_line + 1
        docstring = _get_preceding_docstring(node, self.source_bytes)

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

    def _visit_variable_declaration(self, node: Node):
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

                    is_async = any(c.type == "async" for c in val_node.children)
                    body_node = val_node.child_by_field_name("body")
                    calls = self._extract_calls(body_node, is_method=False) if body_node else []

                    start_line = node.start_point.row + 1
                    end_line = node.end_point.row + 1
                    line_count = end_line - start_line + 1
                    docstring = _get_preceding_docstring(node, self.source_bytes)

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
                            is_async = any(c.type == "async" for c in prop.children)
                            body_node = prop.child_by_field_name("body")
                            calls = self._extract_calls(body_node, is_method=False) if body_node else []
                            start_line = prop.start_point.row + 1
                            end_line = prop.end_point.row + 1
                            line_count = end_line - start_line + 1
                            docstring = _get_preceding_docstring(prop, self.source_bytes)

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
                            is_async = any(c.type == "async" for c in val_func.children)
                            body_node = val_func.child_by_field_name("body")
                            calls = self._extract_calls(body_node, is_method=False) if body_node else []
                            start_line = prop.start_point.row + 1
                            end_line = prop.end_point.row + 1
                            line_count = end_line - start_line + 1
                            docstring = _get_preceding_docstring(prop, self.source_bytes)

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
            tree = self._parser.parse(source_bytes)
            root = tree.root_node

            parse_errors: List[str] = []
            if root.has_error:
                logger.warning("javascript_parse_syntax_warning", path=path)

            visitor = JavaScriptVisitor(module_name, source_bytes)
            visitor.visit(root)

            # Module-level docstring (if first top-level child is comment)
            docstring = None
            if root.named_children and root.named_children[0].type == "comment":
                comment_text = source_bytes[root.named_children[0].start_byte:root.named_children[0].end_byte].decode("utf-8", errors="replace")
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
