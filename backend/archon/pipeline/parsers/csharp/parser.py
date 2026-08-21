"""
C# & .NET Parser (Slice ML-6)

Implements static AST parsing for C# (.cs) source files using tree-sitter.
Emits the canonical language-neutral ParsedFile IR with ASP.NET Core support
without executing repository code.
"""

from collections import Counter
from pathlib import Path
import re
from typing import List, Optional, Set, Tuple
import structlog
from tree_sitter import Language, Parser, Node
import tree_sitter_c_sharp as ts_csharp

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

CS_LANG = Language(ts_csharp.language())


def _derive_csharp_module_name(namespace_name: Optional[str], file_path: str) -> str:
    """
    Derives canonical module name for a C# file.
    If namespace is declared (e.g. 'MyApp.Services'), module_name is 'MyApp.Services.PaymentService'.
    If no namespace is declared, falls back to normalized repository path without .cs.
    """
    stem = Path(file_path).stem
    if namespace_name:
        return f"{namespace_name}.{stem}"

    # Fallback to normalized repo path
    norm = file_path.replace("\\", "/").strip("/")
    if norm.endswith(".cs"):
        norm = norm[:-3]
    return norm.replace("/", ".")


def _clean_xml_docstring(raw_comment: Optional[str]) -> Optional[str]:
    """Cleans a C# XML doc comment string (e.g. '/// <summary> text </summary>')."""
    if not raw_comment:
        return None
    lines = raw_comment.strip().splitlines()
    cleaned_lines = []
    for line in lines:
        l = line.strip()
        if l.startswith("///"):
            l = l[3:].strip()
        elif l.startswith("//"):
            l = l[2:].strip()
        elif l.startswith("/*") or l.startswith("*/") or l.startswith("*"):
            l = l.lstrip("/*").rstrip("*/").strip()

        # Strip XML tags e.g. <summary>, </summary>, <param name="x">, etc.
        l = re.sub(r"<[^>]+>", "", l).strip()
        if l:
            cleaned_lines.append(l)

    cleaned = "\n".join(cleaned_lines)
    return cleaned if cleaned else None


class CSharpVisitor:
    """
    Walks tree-sitter C# AST to extract universal IR facts:
      - File-scoped and block namespace declarations & module_name
      - Standard, static, global, and alias using directives
      - Classes, records, structs, interfaces, and enums
      - Inheritance & implemented interfaces
      - Constructors & methods with overload differentiation
      - ASP.NET Core attributes and decorators
      - Method invocations with 3-state call resolution
      - Cyclomatic complexity & nesting depth
    """

    def __init__(self, source_bytes: bytes, file_path: str):
        self.source_bytes = source_bytes
        self.file_path = file_path
        self.namespace_name: Optional[str] = None
        self.imports: List[ParsedImport] = []
        self.classes: List[ParsedClass] = []
        self.file_docstring: Optional[str] = None
        self.parse_errors: List[str] = []

    def _text(self, node: Optional[Node]) -> str:
        if node is None:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _find_preceding_docstring(self, node: Node) -> Optional[str]:
        """Finds preceding XML doc comment (/// ...) before a node."""
        comments: List[str] = []
        curr = node.prev_named_sibling
        while curr and curr.type == "comment":
            c_text = self._text(curr)
            if c_text.startswith("///") or c_text.startswith("/**"):
                comments.insert(0, c_text)
            curr = curr.prev_named_sibling

        if comments:
            return _clean_xml_docstring("\n".join(comments))
        return None

    def visit_compilation_unit(self, root: Node) -> Tuple[Optional[str], List[ParsedImport], List[ParsedClass], Optional[str]]:
        self._walk_top_level(root)
        module_name = _derive_csharp_module_name(self.namespace_name, self.file_path)
        return module_name, self.imports, self.classes, self.file_docstring

    def _walk_top_level(self, parent_node: Node):
        for child in parent_node.children:
            if child.type == "file_scoped_namespace_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    self.namespace_name = self._text(name_node)
                # Parse body of file-scoped namespace
                self._walk_top_level(child)

            elif child.type == "namespace_declaration":
                name_node = child.child_by_field_name("name")
                if name_node and not self.namespace_name:
                    self.namespace_name = self._text(name_node)
                body_node = child.child_by_field_name("body")
                if body_node:
                    self._walk_top_level(body_node)

            elif child.type == "using_directive":
                self._visit_using_directive(child)

            elif child.type in ("class_declaration", "record_declaration", "struct_declaration", "interface_declaration", "enum_declaration"):
                cls = self._visit_type_declaration(child, parent_qname=None)
                if cls:
                    self.classes.append(cls)

    def _visit_using_directive(self, node: Node):
        """Extracts using directive: standard, alias, static, or global."""
        alias_name: Optional[str] = None
        target_name = ""

        children = [c for c in node.children if c.type not in (";", "using", "global", "static")]
        has_equals = any(c.type == "=" for c in children)

        if has_equals:
            for i, c in enumerate(children):
                if c.type == "=" and i > 0:
                    alias_name = self._text(children[i - 1])
                elif c.type in ("qualified_name", "identifier") and i > 0:
                    target_name = self._text(c)
        else:
            for c in children:
                if c.type in ("qualified_name", "identifier"):
                    target_name = self._text(c)

        if not target_name:
            return

        if "." in target_name:
            parts = target_name.rsplit(".", 1)
            self.imports.append(ParsedImport(
                name=parts[1],
                alias=alias_name,
                is_from_import=True,
                module=parts[0]
            ))
        else:
            self.imports.append(ParsedImport(
                name=target_name,
                alias=alias_name,
                is_from_import=False,
                module=None
            ))

    def _extract_attributes(self, node: Node) -> List[str]:
        """Extracts C# attributes e.g. [ApiController], [Route(\"api/[controller]\")]."""
        attributes: List[str] = []
        for child in node.children:
            if child.type == "attribute_list":
                for attr in child.children:
                    if attr.type == "attribute":
                        attributes.append(f"[{self._text(attr)}]")
        return attributes

    def _visit_type_declaration(self, node: Node, parent_qname: Optional[str]) -> Optional[ParsedClass]:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        class_name = self._text(name_node)
        module_name = _derive_csharp_module_name(self.namespace_name, self.file_path)
        class_qname = f"{parent_qname}.{class_name}" if parent_qname else f"{module_name}.{class_name}"

        # Base types & interfaces (base_list)
        base_classes: List[str] = []
        base_list_node = node.child_by_field_name("bases")
        if not base_list_node:
            # Fallback check for child of type base_list
            for c in node.children:
                if c.type == "base_list":
                    base_list_node = c
                    break

        if base_list_node:
            for child in base_list_node.children:
                if child.type in ("identifier", "qualified_name", "generic_name"):
                    base_classes.append(self._text(child))

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
                elif child.type in ("class_declaration", "record_declaration", "struct_declaration", "interface_declaration", "enum_declaration"):
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
            if child.type in ("parameter", "implicit_type_parameter"):
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

        decorators = self._extract_attributes(node)
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

        decorators = self._extract_attributes(node)

        ret_node = node.child_by_field_name("type")
        return_annotation = self._text(ret_node) if ret_node else None

        # Check async keyword modifier or Task return type
        is_async = False
        for c in node.children:
            if c.type == "modifier" and self._text(c) == "async":
                is_async = True
                break
        if return_annotation and ("Task" in return_annotation or "ValueTask" in return_annotation):
            is_async = True

        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = max(1, end_line - start_line + 1)
        docstring = self._find_preceding_docstring(node)

        # Check either block body or expression arrow body (=> expr)
        body_node = node.child_by_field_name("body")
        if not body_node:
            for c in node.children:
                if c.type == "arrow_expression_clause":
                    body_node = c
                    break

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
            # 1. Method invocation: receiver.Method() or Method()
            if n.type == "invocation_expression":
                expr_node = n.child_by_field_name("function")
                if not expr_node and n.children:
                    expr_node = n.children[0]

                if expr_node:
                    if expr_node.type == "member_access_expression":
                        # receiver.Method()
                        name_sub = expr_node.child_by_field_name("name")
                        rec_sub = expr_node.child_by_field_name("expression")
                        if name_sub:
                            method_name = self._text(name_sub)
                            rec_text = self._text(rec_sub) if rec_sub else ""
                            if rec_text in ("this", "base"):
                                resolution = "inferred"
                            else:
                                resolution = "unresolved"

                            calls.append(ResolvedCall(
                                raw_name=method_name,
                                target_qualified_name=None,
                                resolution=resolution
                            ))
                    elif expr_node.type in ("identifier", "generic_name"):
                        # Bare local method call: Validate(id)
                        method_name = self._text(expr_node)
                        calls.append(ResolvedCall(
                            raw_name=method_name,
                            target_qualified_name=None,
                            resolution="inferred"
                        ))

            # 2. Object creation: new PaymentService()
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
        Computes Cyclomatic Complexity for C# method.
        Base complexity = 1.
        Branches: if, for, foreach, while, do, catch, switch arm/section, ternary (? :), binary && / ||, null-coalescing (??).
        """
        if not body_node:
            return 1

        complexity = 1
        branch_types = {
            "if_statement",
            "for_statement",
            "for_each_statement",
            "while_statement",
            "do_statement",
            "catch_clause",
            "conditional_expression",
            "null_coalescing_expression",
            "&&", "||"
        }

        stack = [body_node]
        while stack:
            n = stack.pop()
            if n.type in branch_types and n != body_node:
                complexity += 1
            elif n.type in ("switch_section", "switch_expression_arm"):
                if not any(c.type == "default_switch_label" for c in n.children):
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
            "for_each_statement",
            "while_statement",
            "do_statement",
            "try_statement",
            "catch_clause",
            "switch_statement",
            "switch_expression",
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


class CSharpParser(LanguageParser):
    """
    Production-quality C# (.cs) language parser conforming to Archon's
    universal language-neutral contract.
    """

    def __init__(self):
        self._parser = Parser(CS_LANG)

    @property
    def language(self) -> str:
        return "csharp"

    @property
    def file_extensions(self) -> List[str]:
        return [".cs"]

    def parse_file(self, path: str, content: str) -> ParsedFile:
        total_lines = max(1, len(content.splitlines()))

        try:
            source_bytes = content.encode("utf-8", errors="replace")
            tree = self._parser.parse(source_bytes)

            visitor = CSharpVisitor(source_bytes, path)
            module_name, imports, classes, docstring = visitor.visit_compilation_unit(tree.root_node)

            return ParsedFile(
                path=path,
                language=self.language,
                module_name=module_name,
                total_lines=total_lines,
                docstring=docstring,
                classes=classes,
                functions=[],  # In C#, all executable units belong to classes/structs/records
                imports=imports,
                parse_errors=visitor.parse_errors
            )

        except Exception as e:
            logger.error("csharp_parser_error", path=path, error=str(e))
            return ParsedFile(
                path=path,
                language=self.language,
                module_name=_derive_csharp_module_name(None, path),
                total_lines=total_lines,
                docstring=None,
                classes=[],
                functions=[],
                imports=[],
                parse_errors=[f"parse_error: {str(e)}"]
            )


# Auto-register CSharpParser to the production registry
registry.register(CSharpParser())
