"""
Go Language Parser (Slice ML-7)

Implements static AST parsing for Go (.go) source files using tree-sitter.
Emits the canonical language-neutral ParsedFile IR without executing repository code.
"""

from collections import Counter
from pathlib import Path
from typing import List, Optional, Set, Tuple, Dict
import structlog
from tree_sitter import Language, Parser, Node
import tree_sitter_go as ts_go

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

GO_LANG = Language(ts_go.language())


def _derive_go_module_name(package_name: Optional[str], file_path: str) -> str:
    """
    Derives canonical module name for a Go file.
    If package is declared (e.g. 'orders'), module_name is 'orders.OrderService'.
    If no package is declared, falls back to normalized repository path without .go.
    """
    stem = Path(file_path).stem
    if package_name:
        return f"{package_name}.{stem}"

    # Fallback to normalized repo path
    norm = file_path.replace("\\", "/").strip("/")
    if norm.endswith(".go"):
        norm = norm[:-3]
    return norm.replace("/", ".")


def _clean_docstring(raw_comment: Optional[str]) -> Optional[str]:
    """Cleans a Go doc comment (// ... or /* ... */)."""
    if not raw_comment:
        return None
    lines = raw_comment.strip().splitlines()
    cleaned_lines = []
    for line in lines:
        l = line.strip()
        if l.startswith("//"):
            l = l[2:].strip()
        elif l.startswith("/*") or l.startswith("*/") or l.startswith("*"):
            l = l.lstrip("/*").rstrip("*/").strip()
        if l:
            cleaned_lines.append(l)

    cleaned = "\n".join(cleaned_lines)
    return cleaned if cleaned else None


class GoVisitor:
    """
    Walks tree-sitter Go AST to extract universal IR facts:
      - Package declarations & module_name
      - Standard, aliased, blank, and factored imports
      - Structs and interfaces as ParsedClass entities
      - Embedded struct inheritance
      - Top-level functions and receiver methods as ParsedFunction entities
      - Function calls with strict 3-state call resolution
      - Cyclomatic complexity & nesting depth
    """

    def __init__(self, source_bytes: bytes, file_path: str):
        self.source_bytes = source_bytes
        self.file_path = file_path
        self.package_name: Optional[str] = None
        self.imports: List[ParsedImport] = []
        self.classes: List[ParsedClass] = []
        self.functions: List[ParsedFunction] = []
        self.file_docstring: Optional[str] = None
        self.parse_errors: List[str] = []

    def _text(self, node: Optional[Node]) -> str:
        if node is None:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _find_preceding_docstring(self, node: Node) -> Optional[str]:
        """Finds preceding comments (// ...) before a node."""
        comments: List[str] = []
        curr = node.prev_named_sibling
        while curr and curr.type == "comment":
            comments.insert(0, self._text(curr))
            curr = curr.prev_named_sibling

        if comments:
            return _clean_docstring("\n".join(comments))
        return None

    def visit_source_file(self, root: Node) -> Tuple[Optional[str], List[ParsedImport], List[ParsedClass], List[ParsedFunction], Optional[str]]:
        classes_by_name: Dict[str, ParsedClass] = {}

        # 1. First pass: extract package, imports, and type declarations (structs & interfaces)
        for child in root.children:
            if child.type == "package_clause":
                pkg_id = child.child_by_field_name("name")
                if not pkg_id:
                    # In tree-sitter-go, package_identifier is a child
                    for sub in child.children:
                        if sub.type == "package_identifier":
                            pkg_id = sub
                            break
                if pkg_id:
                    self.package_name = self._text(pkg_id)
                if not self.file_docstring:
                    self.file_docstring = self._find_preceding_docstring(child)

            elif child.type == "import_declaration":
                self._visit_import_declaration(child)

            elif child.type == "type_declaration":
                self._visit_type_declaration(child, classes_by_name)

        module_name = _derive_go_module_name(self.package_name, self.file_path)

        # 2. Second pass: extract functions and methods
        for child in root.children:
            if child.type == "function_declaration":
                func = self._visit_function(child, module_name)
                if func:
                    self.functions.append(func)

            elif child.type == "method_declaration":
                self._visit_method(child, module_name, classes_by_name)

        self.classes = list(classes_by_name.values())
        return module_name, self.imports, self.classes, self.functions, self.file_docstring

    def _visit_import_declaration(self, node: Node):
        """Extracts single or factored import declarations."""
        def process_spec(spec_node: Node):
            path_node = spec_node.child_by_field_name("path")
            name_node = spec_node.child_by_field_name("name")

            if not path_node:
                return

            raw_path = self._text(path_node).strip('"\'`')
            alias = self._text(name_node) if name_node else None

            if "/" in raw_path:
                parts = raw_path.rsplit("/", 1)
                self.imports.append(ParsedImport(
                    name=parts[1],
                    alias=alias,
                    is_from_import=True,
                    module=parts[0]
                ))
            else:
                self.imports.append(ParsedImport(
                    name=raw_path,
                    alias=alias,
                    is_from_import=False,
                    module=None
                ))

        for child in node.children:
            if child.type == "import_spec":
                process_spec(child)
            elif child.type == "import_spec_list":
                for sub in child.children:
                    if sub.type == "import_spec":
                        process_spec(sub)

    def _visit_type_declaration(self, node: Node, classes_by_name: Dict[str, ParsedClass]):
        """Extracts struct types and interface types into ParsedClass entities."""
        docstring = self._find_preceding_docstring(node)
        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = max(1, end_line - start_line + 1)
        module_name = _derive_go_module_name(self.package_name, self.file_path)

        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")

                if not name_node or not type_node:
                    continue

                type_name = self._text(name_node)
                class_qname = f"{module_name}.{type_name}"

                base_classes: List[str] = []

                if type_node.type == "struct_type":
                    # Extract embedded fields (anonymous fields)
                    for sub in type_node.children:
                        if sub.type == "field_declaration_list":
                            for field in sub.children:
                                if field.type == "field_declaration":
                                    has_field_id = any(c.type == "field_identifier" for c in field.children)
                                    if not has_field_id:
                                        for c in field.children:
                                            if c.type == "type_identifier":
                                                base_classes.append(self._text(c))

                elif type_node.type == "interface_type":
                    # Extract embedded interfaces
                    for item in type_node.children:
                        if item.type == "type_identifier":
                            base_classes.append(self._text(item))

                parsed_cls = ParsedClass(
                    name=type_name,
                    qualified_name=class_qname,
                    base_classes=base_classes,
                    methods=[],
                    start_line=start_line,
                    end_line=end_line,
                    line_count=line_count,
                    docstring=docstring
                )
                classes_by_name[type_name] = parsed_cls

    def _extract_parameters(self, params_node: Optional[Node]) -> List[str]:
        """Extracts parameter names."""
        param_names: List[str] = []
        if not params_node:
            return param_names

        for child in params_node.children:
            if child.type == "parameter_declaration":
                n_node = child.child_by_field_name("name")
                if n_node:
                    param_names.append(self._text(n_node))
        return param_names

    def _visit_function(self, node: Node, module_name: str) -> Optional[ParsedFunction]:
        """Extracts top-level Go function."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        func_name = self._text(name_node)
        func_qname = f"{module_name}.{func_name}"

        params_node = node.child_by_field_name("parameters")
        param_names = self._extract_parameters(params_node)

        ret_node = node.child_by_field_name("result")
        return_annotation = self._text(ret_node) if ret_node else None

        docstring = self._find_preceding_docstring(node)
        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = max(1, end_line - start_line + 1)

        body_node = node.child_by_field_name("body")
        calls = self._extract_calls(body_node, receiver_var=None) if body_node else []
        complexity = self._calculate_complexity(body_node) if body_node else 1
        nesting = self._calculate_nesting_depth(body_node) if body_node else 0

        return ParsedFunction(
            name=func_name,
            qualified_name=func_qname,
            parameters=param_names,
            decorators=[],
            return_annotation=return_annotation,
            is_method=False,
            is_async=False,
            cyclomatic_complexity=complexity,
            nesting_depth=nesting,
            start_line=start_line,
            end_line=end_line,
            line_count=line_count,
            docstring=docstring,
            calls=calls
        )

    def _visit_method(self, node: Node, module_name: str, classes_by_name: Dict[str, ParsedClass]):
        """Extracts receiver method and attaches it to its receiver struct class."""
        name_node = node.child_by_field_name("name")
        rec_node = node.child_by_field_name("receiver")

        if not name_node or not rec_node:
            return

        method_name = self._text(name_node)
        receiver_var: Optional[str] = None
        receiver_type: str = ""

        # Receiver is e.g. (s *OrderService) or (s OrderService) or (*OrderService)
        for param in rec_node.children:
            if param.type == "parameter_declaration":
                n_sub = param.child_by_field_name("name")
                t_sub = param.child_by_field_name("type")
                if n_sub:
                    receiver_var = self._text(n_sub)
                if t_sub:
                    receiver_type = self._text(t_sub).lstrip("*").strip()

        if not receiver_type:
            receiver_type = "Unknown"

        method_qname = f"{module_name}.{receiver_type}.{method_name}"

        params_node = node.child_by_field_name("parameters")
        param_names = self._extract_parameters(params_node)

        ret_node = node.child_by_field_name("result")
        return_annotation = self._text(ret_node) if ret_node else None

        docstring = self._find_preceding_docstring(node)
        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        line_count = max(1, end_line - start_line + 1)

        body_node = node.child_by_field_name("body")
        calls = self._extract_calls(body_node, receiver_var=receiver_var) if body_node else []
        complexity = self._calculate_complexity(body_node) if body_node else 1
        nesting = self._calculate_nesting_depth(body_node) if body_node else 0

        parsed_method = ParsedFunction(
            name=method_name,
            qualified_name=method_qname,
            parameters=param_names,
            decorators=[],
            return_annotation=return_annotation,
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

        if receiver_type in classes_by_name:
            classes_by_name[receiver_type].methods.append(parsed_method)
        else:
            # If the struct was declared elsewhere, keep method visible in functions
            self.functions.append(parsed_method)

    def _extract_calls(self, body_node: Optional[Node], receiver_var: Optional[str]) -> List[ResolvedCall]:
        """Extracts function and method invocations with strict 3-state resolution."""
        calls: List[ResolvedCall] = []
        if not body_node:
            return calls

        def walk(n: Node):
            if n.type == "call_expression":
                fn_node = n.child_by_field_name("function")
                if fn_node:
                    if fn_node.type == "identifier":
                        # Bare function call: validate(id) -> inferred
                        calls.append(ResolvedCall(
                            raw_name=self._text(fn_node),
                            target_qualified_name=None,
                            resolution="inferred"
                        ))
                    elif fn_node.type == "selector_expression":
                        # operand.field e.g. s.validate(), repo.Find(), fmt.Println()
                        op_node = fn_node.child_by_field_name("operand")
                        field_node = fn_node.child_by_field_name("field")
                        if field_node:
                            method_name = self._text(field_node)
                            op_text = self._text(op_node) if op_node else ""
                            if receiver_var and op_text == receiver_var:
                                resolution = "inferred"
                            else:
                                resolution = "unresolved"

                            calls.append(ResolvedCall(
                                raw_name=method_name,
                                target_qualified_name=None,
                                resolution=resolution
                            ))

            for child in n.children:
                walk(child)

        walk(body_node)
        return calls

    def _calculate_complexity(self, body_node: Optional[Node]) -> int:
        """
        Computes Cyclomatic Complexity for Go function/method.
        Base complexity = 1.
        Branches: if, for, expression_case_clause, type_case_clause, communication_case, binary && / ||.
        """
        if not body_node:
            return 1

        complexity = 1

        def walk(n: Node):
            nonlocal complexity
            if n.type in (
                "if_statement",
                "for_statement",
                "expression_case",
                "type_case",
                "communication_case",
            ):
                complexity += 1
            elif n.type == "binary_expression":
                op_node = n.child_by_field_name("operator")
                if op_node and self._text(op_node) in ("&&", "||"):
                    complexity += 1

            for child in n.children:
                walk(child)

        walk(body_node)
        return complexity

    def _calculate_nesting_depth(self, body_node: Optional[Node]) -> int:
        """Computes maximum control flow nesting depth."""
        if not body_node:
            return 0

        max_depth = 0
        nesting_types = {
            "if_statement",
            "for_statement",
            "expression_switch_statement",
            "type_switch_statement",
            "select_statement",
        }

        def walk(n: Node, current_depth: int):
            nonlocal max_depth
            is_branch = n.type in nesting_types
            new_depth = current_depth + 1 if is_branch else current_depth
            if new_depth > max_depth:
                max_depth = new_depth

            for child in n.children:
                walk(child, new_depth)

        walk(body_node, 0)
        return max_depth


class GoParser(LanguageParser):
    """
    Production-quality Go (.go) language parser conforming to Archon's
    universal language-neutral contract.
    """

    def __init__(self):
        self._parser = Parser(GO_LANG)

    @property
    def language(self) -> str:
        return "go"

    @property
    def file_extensions(self) -> List[str]:
        return [".go"]

    def parse_file(self, path: str, content: str) -> ParsedFile:
        total_lines = max(1, len(content.splitlines()))

        try:
            source_bytes = content.encode("utf-8", errors="replace")
            tree = self._parser.parse(source_bytes)

            visitor = GoVisitor(source_bytes, path)
            module_name, imports, classes, functions, docstring = visitor.visit_source_file(tree.root_node)

            return ParsedFile(
                path=path,
                language=self.language,
                module_name=module_name,
                total_lines=total_lines,
                docstring=docstring,
                classes=classes,
                functions=functions,
                imports=imports,
                parse_errors=visitor.parse_errors
            )

        except Exception as e:
            logger.error("go_parser_error", path=path, error=str(e))
            return ParsedFile(
                path=path,
                language=self.language,
                module_name=_derive_go_module_name(None, path),
                total_lines=total_lines,
                docstring=None,
                classes=[],
                functions=[],
                imports=[],
                parse_errors=[f"parse_error: {str(e)}"]
            )


# Auto-register GoParser to the production registry
registry.register(GoParser())
