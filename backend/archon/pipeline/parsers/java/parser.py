"""
Java & Spring Boot Parser (Slice ML-5)

Implements static AST parsing for Java (.java) source files using tree-sitter.
Emits the canonical language-neutral ParsedFile IR without repository code execution.
"""

from collections import Counter
from pathlib import Path
from typing import List, Optional, Set, Tuple
import structlog
from tree_sitter import Language, Parser, Node
import tree_sitter_java as ts_java

from archon.pipeline.parsers.base import (
    LanguageParser,
    ParsedFile,
    ParsedClass,
    ParsedFunction,
    ParsedImport,
    ResolvedCall,
)
from archon.pipeline.parsers.registry import registry

logger = structlog.get_logger(__name__)

JAVA_LANG = Language(ts_java.language())


def _derive_java_module_name(package_name: Optional[str], file_path: str) -> str:
    """
    Derives canonical module name for a Java file.
    If package is declared (e.g. 'com.example.service'), module_name is 'com.example.service.OrderService'.
    If no package is declared, falls back to normalized repository path without .java.
    """
    stem = Path(file_path).stem
    if package_name:
        return f"{package_name}.{stem}"
    
    # Fallback to normalized repo path
    norm = file_path.replace("\\", "/").strip("/")
    if norm.endswith(".java"):
        norm = norm[:-5]
    return norm.replace("/", ".")


def _clean_docstring(raw_comment: Optional[str]) -> Optional[str]:
    """Cleans a Javadoc comment string."""
    if not raw_comment:
        return None
    raw = raw_comment.strip()
    if raw.startswith("/**") and raw.endswith("*/"):
        raw = raw[3:-2].strip()
        lines = [line.strip().lstrip("*").strip() for line in raw.split("\n")]
        cleaned = "\n".join(line for line in lines if line)
        return cleaned if cleaned else None
    return None


class JavaVisitor:
    """
    Walks tree-sitter Java AST to extract universal IR facts:
      - Package declarations & module_name
      - Standard, static, and wildcard imports
      - Classes, records, interfaces, and enums
      - Inheritance & implemented interfaces
      - Constructors & methods with overload differentiation
      - Spring Boot and standard annotations (decorators)
      - Method invocations with 3-state call resolution
      - Cyclomatic complexity & nesting depth
    """

    def __init__(self, source_bytes: bytes, file_path: str):
        self.source_bytes = source_bytes
        self.file_path = file_path
        self.package_name: Optional[str] = None
        self.imports: List[ParsedImport] = []
        self.classes: List[ParsedClass] = []
        self.file_docstring: Optional[str] = None
        self.parse_errors: List[str] = []

    def _text(self, node: Optional[Node]) -> str:
        if node is None:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _find_preceding_docstring(self, node: Node) -> Optional[str]:
        """Finds Javadoc block comment preceding a node."""
        prev = node.prev_named_sibling
        if prev and prev.type == "block_comment":
            comment_text = self._text(prev)
            if comment_text.startswith("/**"):
                return _clean_docstring(comment_text)
        return None

    def visit_program(self, root: Node) -> Tuple[Optional[str], List[ParsedImport], List[ParsedClass], Optional[str]]:
        # 1. First pass: extract package declaration and file docstring
        for child in root.children:
            if child.type == "package_declaration":
                # package com.example.service;
                for sub in child.children:
                    if sub.type in ("scoped_identifier", "identifier"):
                        self.package_name = self._text(sub)
                if not self.file_docstring:
                    self.file_docstring = self._find_preceding_docstring(child)

            elif child.type == "import_declaration":
                self._visit_import(child)

            elif child.type in ("class_declaration", "record_declaration", "interface_declaration", "enum_declaration"):
                cls = self._visit_type_declaration(child, parent_qname=None)
                if cls:
                    self.classes.append(cls)

        module_name = _derive_java_module_name(self.package_name, self.file_path)
        return module_name, self.imports, self.classes, self.file_docstring

    def _visit_import(self, node: Node):
        """Extracts import statement: normal, wildcard, static, and static wildcard."""
        is_static = any(c.type == "static" for c in node.children)
        is_wildcard = any(c.type == "asterisk" for c in node.children)

        import_target = ""
        for c in node.children:
            if c.type in ("scoped_identifier", "identifier"):
                import_target = self._text(c)

        if not import_target:
            return

        if is_wildcard:
            self.imports.append(ParsedImport(
                name="*",
                alias=None,
                is_from_import=True,
                module=import_target
            ))
        else:
            if "." in import_target:
                parts = import_target.rsplit(".", 1)
                self.imports.append(ParsedImport(
                    name=parts[1],
                    alias=None,
                    is_from_import=True,
                    module=parts[0]
                ))
            else:
                self.imports.append(ParsedImport(
                    name=import_target,
                    alias=None,
                    is_from_import=False,
                    module=None
                ))

    def _extract_annotations(self, node: Node) -> List[str]:
        """Extracts annotations as decorators: e.g. ['@Service', '@GetMapping(\"/users\")']."""
        decorators: List[str] = []
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type in ("annotation", "marker_annotation"):
                        decorators.append(self._text(mod))
            elif child.type in ("annotation", "marker_annotation"):
                decorators.append(self._text(child))
        return decorators

    def _visit_type_declaration(self, node: Node, parent_qname: Optional[str]) -> Optional[ParsedClass]:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        class_name = self._text(name_node)
        module_name = _derive_java_module_name(self.package_name, self.file_path)
        class_qname = f"{parent_qname}.{class_name}" if parent_qname else f"{module_name}.{class_name}"

        # Superclass & Interfaces
        base_classes: List[str] = []
        superclass_node = node.child_by_field_name("superclass")
        if superclass_node:
            for sub in superclass_node.children:
                if sub.type in ("type_identifier", "generic_type"):
                    base_classes.append(self._text(sub))

        interfaces_node = node.child_by_field_name("interfaces")
        if interfaces_node:
            for sub in interfaces_node.children:
                if sub.type in ("type_list", "interface_type_list"):
                    for iface in sub.children:
                        if iface.type in ("type_identifier", "generic_type"):
                            base_classes.append(self._text(iface))

        docstring = self._find_preceding_docstring(node)
        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = max(1, end_line - start_line + 1)

        body_node = node.child_by_field_name("body")
        methods: List[ParsedFunction] = []

        if body_node:
            # 1. Count method names to identify overloads
            method_name_counts: Counter = Counter()
            body_children = body_node.children

            for child in body_children:
                if child.type == "method_declaration":
                    mname_node = child.child_by_field_name("name")
                    if mname_node:
                        method_name_counts[self._text(mname_node)] += 1
                elif child.type == "constructor_declaration":
                    cname_node = child.child_by_field_name("name")
                    if cname_node:
                        method_name_counts[self._text(cname_node)] += 1

            # 2. Extract methods and constructors
            for child in body_children:
                if child.type == "constructor_declaration":
                    m = self._visit_constructor(child, class_qname, method_name_counts)
                    if m:
                        methods.append(m)
                elif child.type == "method_declaration":
                    m = self._visit_method(child, class_qname, method_name_counts)
                    if m:
                        methods.append(m)
                elif child.type in ("class_declaration", "record_declaration", "interface_declaration", "enum_declaration"):
                    nested_cls = self._visit_type_declaration(child, parent_qname=class_qname)
                    if nested_cls:
                        self.classes.append(nested_cls)

        return ParsedClass(
            name=class_name,
            qualified_name=class_qname,
            base_classes=base_classes,
            methods=methods,
            start_line=start_line,
            end_line=end_line,
            line_count=line_count,
            docstring=docstring
        )

    def _extract_parameters(self, params_node: Optional[Node]) -> Tuple[List[str], List[str]]:
        """Extracts parameter names and parameter types."""
        param_names: List[str] = []
        param_types: List[str] = []
        if not params_node:
            return param_names, param_types

        for child in params_node.children:
            if child.type in ("formal_parameter", "spread_parameter"):
                t_node = child.child_by_field_name("type")
                n_node = child.child_by_field_name("name")
                if t_node:
                    param_types.append(self._text(t_node))
                if n_node:
                    param_names.append(self._text(n_node))
        return param_names, param_types

    def _visit_constructor(
        self,
        node: Node,
        class_qname: str,
        name_counts: Counter
    ) -> Optional[ParsedFunction]:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = self._text(name_node)
        params_node = node.child_by_field_name("parameters")
        param_names, param_types = self._extract_parameters(params_node)

        # Overload handling
        if name_counts[name] > 1:
            method_qname = f"{class_qname}.{name}({','.join(param_types)})"
        else:
            method_qname = f"{class_qname}.{name}"

        decorators = self._extract_annotations(node)

        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = max(1, end_line - start_line + 1)
        docstring = self._find_preceding_docstring(node)

        body_node = node.child_by_field_name("body")
        calls = self._extract_calls(body_node) if body_node else []
        complexity = self._calculate_complexity(body_node) if body_node else 1
        nesting = self._calculate_nesting_depth(body_node) if body_node else 0

        return ParsedFunction(
            name=name,
            qualified_name=method_qname,
            parameters=param_names,
            decorators=decorators,
            return_annotation=None,
            is_method=True,
            is_async=False,
            cyclomatic_complexity=complexity,
            nesting_depth=nesting,
            start_line=start_line,
            end_line=end_line,
            line_count=line_count,
            docstring=docstring,
            calls=calls
        )

    def _visit_method(
        self,
        node: Node,
        class_qname: str,
        name_counts: Counter
    ) -> Optional[ParsedFunction]:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = self._text(name_node)
        params_node = node.child_by_field_name("parameters")
        param_names, param_types = self._extract_parameters(params_node)

        # Overload handling: distinct signature suffix when overloaded
        if name_counts[name] > 1:
            method_qname = f"{class_qname}.{name}({','.join(param_types)})"
        else:
            method_qname = f"{class_qname}.{name}"

        decorators = self._extract_annotations(node)

        # Check @Async annotation
        is_async = any("@Async" in d for d in decorators)

        ret_node = node.child_by_field_name("type")
        return_annotation = self._text(ret_node) if ret_node else None

        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = max(1, end_line - start_line + 1)
        docstring = self._find_preceding_docstring(node)

        body_node = node.child_by_field_name("body")
        calls = self._extract_calls(body_node) if body_node else []
        complexity = self._calculate_complexity(body_node) if body_node else 1
        nesting = self._calculate_nesting_depth(body_node) if body_node else 0

        return ParsedFunction(
            name=name,
            qualified_name=method_qname,
            parameters=param_names,
            decorators=decorators,
            return_annotation=return_annotation,
            is_method=True,
            is_async=is_async,
            cyclomatic_complexity=complexity,
            nesting_depth=nesting,
            start_line=start_line,
            end_line=end_line,
            line_count=line_count,
            docstring=docstring,
            calls=calls
        )

    def _extract_calls(self, body_node: Optional[Node]) -> List[ResolvedCall]:
        """Extracts method invocations with strict 3-state resolution."""
        calls: List[ResolvedCall] = []
        if not body_node:
            return calls

        def walk(n: Node):
            # 1. Method invocation: object.method() or method()
            if n.type == "method_invocation":
                name_node = n.child_by_field_name("name")
                obj_node = n.child_by_field_name("object")
                if name_node:
                    method_name = self._text(name_node)
                    if obj_node:
                        obj_text = self._text(obj_node)
                        if obj_text in ("this", "super"):
                            resolution = "inferred"
                        else:
                            resolution = "unresolved"
                    else:
                        resolution = "inferred"  # In-scope bare method call

                    calls.append(ResolvedCall(
                        raw_name=method_name,
                        target_qualified_name=None,
                        resolution=resolution
                    ))

            # 2. Object creation: new MyService()
            elif n.type == "object_creation_expression":
                type_node = n.child_by_field_name("type")
                if type_node:
                    type_name = self._text(type_node)
                    calls.append(ResolvedCall(
                        raw_name=type_name,
                        target_qualified_name=None,
                        resolution="unresolved"
                    ))

            for child in n.children:
                walk(child)

        walk(body_node)
        return calls

    def _calculate_complexity(self, body_node: Optional[Node]) -> int:
        """
        Computes Cyclomatic Complexity for Java method.
        Base complexity = 1.
        Branches: if, for, enhanced_for, while, do, catch, ternary, binary && / ||, switch case.
        """
        if not body_node:
            return 1

        complexity = 1
        branch_types = {
            "if_statement",
            "for_statement",
            "enhanced_for_statement",
            "while_statement",
            "do_statement",
            "catch_clause",
            "ternary_expression",
            "&&", "||"
        }

        stack = [body_node]
        while stack:
            n = stack.pop()
            if n.type in branch_types and n != body_node:
                complexity += 1
            elif n.type in ("switch_label", "switch_rule"):
                if not any(c.type == "default" for c in n.children):
                    complexity += 1
            for child in n.children:
                stack.append(child)

        return complexity

    def _calculate_nesting_depth(self, body_node: Optional[Node]) -> int:
        """Computes maximum control flow nesting depth."""
        if not body_node:
            return 0

        nesting_types = {
            "if_statement",
            "for_statement",
            "enhanced_for_statement",
            "while_statement",
            "do_statement",
            "try_statement",
            "catch_clause",
            "switch_expression",
            "switch_statement",
        }

        max_depth = 0
        stack = [(body_node, 0)]
        while stack:
            curr, depth = stack.pop()
            if curr.type in nesting_types and curr != body_node:
                depth += 1
            max_depth = max(max_depth, depth)
            for child in curr.children:
                stack.append((child, depth))

        return max_depth


class JavaParser(LanguageParser):
    """
    Production-quality Java (.java) language parser conforming to Archon's
    universal language-neutral contract.
    """

    def __init__(self):
        self._parser = Parser(JAVA_LANG)

    @property
    def language(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> List[str]:
        return [".java"]

    def parse_file(self, path: str, content: str) -> ParsedFile:
        total_lines = max(1, len(content.splitlines()))

        try:
            source_bytes = content.encode("utf-8", errors="replace")
            tree = self._parser.parse(source_bytes)

            visitor = JavaVisitor(source_bytes, path)
            module_name, imports, classes, docstring = visitor.visit_program(tree.root_node)

            return ParsedFile(
                path=path,
                language=self.language,
                module_name=module_name,
                total_lines=total_lines,
                docstring=docstring,
                classes=classes,
                functions=[],  # In Java, all executable units belong to classes
                imports=imports,
                parse_errors=visitor.parse_errors
            )

        except Exception as e:
            logger.error("java_parser_error", path=path, error=str(e))
            return ParsedFile(
                path=path,
                language=self.language,
                module_name=_derive_java_module_name(None, path),
                total_lines=total_lines,
                docstring=None,
                classes=[],
                functions=[],
                imports=[],
                parse_errors=[f"parse_error: {str(e)}"]
            )


# Auto-register JavaParser to the production registry
registry.register(JavaParser())
