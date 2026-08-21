"""
Rust Language Parser (Slice ML-9)

Implements static AST parsing for Rust (.rs) source files using tree-sitter.
Emits the canonical language-neutral ParsedFile IR without executing repository code.

Module Identity Rules:
  - src/lib.rs       -> "lib"      (crate root)
  - src/main.rs      -> "main"     (binary root)
  - src/foo.rs       -> "foo"
  - src/foo/mod.rs   -> "foo"
  - src/a/b.rs       -> "a::b"
  - Cargo.toml package name is read as static metadata only if available,
    and prefixes the module name as "<crate>::<module>". Falls back to
    repository-relative path without that prefix if Cargo.toml is absent.

Qualified name format:  <module_name>.<TypeOrFunction>
  e.g.  "services::billing.BillingService.process_payment"
"""

import re
import posixpath
from pathlib import Path, PurePosixPath
from typing import List, Optional, Dict, Set, Tuple
import structlog
from tree_sitter import Language, Parser, Node
import tree_sitter_rust as ts_rust

from archon.pipeline.parsers.base import (
    LanguageParser,
    ParsedFile,
    ParsedClass,
    ParsedFunction,
    ParsedImport,
    ParsedParameter,
    ResolvedCall,
)
from archon.pipeline.parsers.registry import registry

logger = structlog.get_logger(__name__)

RUST_LANG = Language(ts_rust.language())

# ─────────────────────────────────────────────────────────────────────────────
# Module identity helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_cargo_package_name(file_path: str) -> Optional[str]:
    """
    Reads the [package] name from Cargo.toml, walking upward from the file's
    directory until src/ ancestor is found. Read-only static access; never executes Cargo.
    """
    norm = file_path.replace("\\", "/")
    parts = norm.split("/")

    # Walk up from file location looking for Cargo.toml
    for i in range(len(parts) - 1, 0, -1):
        candidate = "/".join(parts[:i]) + "/Cargo.toml"
        try:
            from pathlib import Path as _Path
            p = _Path(candidate)
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace")
                # Simple static regex parse – never invoke toml library to avoid side-effects
                m = re.search(r'^\[package\].*?^name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE | re.DOTALL)
                if m:
                    return m.group(1)
        except Exception:
            pass
    return None


def _derive_rust_module_name(file_path: str, crate_name: Optional[str] = None) -> str:
    """
    Derives the canonical module name for a Rust source file.

    Rules (in priority order):
      1. src/lib.rs   -> "lib"  (or "<crate>::lib" if crate_name is known)
      2. src/main.rs  -> "main" (or "<crate>::main")
      3. src/foo.rs   -> "foo"  (or "<crate>::foo")
      4. src/a/b.rs   -> "a::b" (or "<crate>::a::b")
      5. src/a/mod.rs -> "a"    (or "<crate>::a")
      6. Fallback: normalized repo-relative path parts joined by "::"
    """
    norm = file_path.replace("\\", "/").strip("/")
    if norm.endswith(".rs"):
        norm = norm[:-3]

    parts = norm.split("/")

    # Find src/ anchor
    src_idx = None
    for i, p in enumerate(parts):
        if p == "src":
            src_idx = i
            break

    if src_idx is not None:
        sub_parts = parts[src_idx + 1:]
    else:
        sub_parts = parts

    # Collapse mod.rs: ['services', 'mod'] -> ['services']
    if sub_parts and sub_parts[-1] == "mod":
        sub_parts = sub_parts[:-1]

    if not sub_parts:
        # e.g. src.rs itself
        module = "crate_root"
    else:
        module = "::".join(sub_parts)

    if crate_name:
        return f"{crate_name}::{module}"
    return module


# ─────────────────────────────────────────────────────────────────────────────
# Doc comment extraction
# ─────────────────────────────────────────────────────────────────────────────

def _clean_rust_doc(raw: str) -> str:
    """Strips Rust doc-comment markers from a comment string."""
    lines = raw.strip().splitlines()
    cleaned: List[str] = []
    for line in lines:
        l = line.strip()
        if l.startswith("///"):
            l = l[3:].strip()
        elif l.startswith("//!"):
            l = l[3:].strip()
        elif l.startswith("//"):
            l = l[2:].strip()
        elif l.startswith("/**") or l.startswith("/*!"):
            l = l[3:].strip()
        elif l.startswith("/*"):
            l = l[2:].strip()
        elif l.endswith("*/"):
            l = l[:-2].strip()
        if l:
            cleaned.append(l)
    return "\n".join(cleaned) if cleaned else ""


def _get_preceding_doc(node: Node, source: bytes) -> Optional[str]:
    """Finds immediately preceding doc comments (///, //!) before a node."""
    comments: List[str] = []
    curr = node.prev_named_sibling
    while curr and curr.type == "line_comment":
        raw = source[curr.start_byte:curr.end_byte].decode("utf-8", errors="replace")
        if raw.strip().startswith("///") or raw.strip().startswith("//!"):
            comments.insert(0, raw)
            curr = curr.prev_named_sibling
        else:
            break
    if not comments:
        return None
    cleaned = _clean_rust_doc("\n".join(comments))
    return cleaned if cleaned else None


def _node_text(node: Optional[Node], source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


# ─────────────────────────────────────────────────────────────────────────────
# Cyclomatic complexity
# ─────────────────────────────────────────────────────────────────────────────

_COMPLEXITY_NODES: Set[str] = {
    "if_expression", "while_expression", "for_expression",
    "loop_expression", "match_arm", "match_expression",
    "closure_expression", "return_expression",
    "break_expression", "continue_expression",
    "try_expression",  # ? operator
}

def _compute_complexity(node: Node) -> int:
    count = 1  # base
    stack = list(node.children)
    while stack:
        n = stack.pop()
        if n.type in _COMPLEXITY_NODES:
            count += 1
        stack.extend(n.children)
    return count


def _compute_nesting(node: Node) -> int:
    """Computes maximum nesting depth within a block/expression."""
    def _depth(n: Node) -> int:
        block_types = {"block", "if_expression", "while_expression",
                       "for_expression", "loop_expression", "match_expression"}
        child_max = max((_depth(c) for c in n.children), default=0)
        if n.type in block_types:
            return child_max + 1
        return child_max
    return _depth(node)


# ─────────────────────────────────────────────────────────────────────────────
# Use clause extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_use_clause(
    node: Node,
    source: bytes,
    prefix: str = "",
) -> List[Tuple[str, Optional[str], str]]:
    """
    Recursively extracts (name, alias, module_path) tuples from a use_declaration.

    Tree-sitter node types handled:
      identifier             -> single import
      scoped_identifier      -> path::name
      use_as_clause          -> path::name as alias
      use_wildcard           -> path::*
      scoped_use_list        -> path::{...}
      use_list               -> {...}
    """
    results: List[Tuple[str, Optional[str], str]] = []

    if node.type == "identifier":
        name = _node_text(node, source)
        results.append((name, None, prefix))

    elif node.type == "scoped_identifier":
        # e.g. crate::utils::format_header
        raw = _node_text(node, source)
        parts = raw.split("::")
        name = parts[-1]
        mod = "::".join(parts[:-1])
        if prefix:
            mod = f"{prefix}::{mod}" if mod else prefix
        results.append((name, None, mod))

    elif node.type == "use_as_clause":
        # e.g. crate::utils::validate as val
        path_node = node.child_by_field_name("path")
        alias_node = node.child_by_field_name("alias")
        path_text = _node_text(path_node, source) if path_node else ""
        alias_text = _node_text(alias_node, source) if alias_node else None

        parts = path_text.split("::")
        name = parts[-1]
        mod = "::".join(parts[:-1])
        if prefix:
            mod = f"{prefix}::{mod}" if mod else prefix
        results.append((name, alias_text, mod))

    elif node.type == "use_wildcard":
        # e.g. super::services::*
        # Children: scoped_identifier or identifier, ::, *
        scope_node = None
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                scope_node = child
                break
        mod = _node_text(scope_node, source) if scope_node else ""
        if prefix:
            mod = f"{prefix}::{mod}" if mod else prefix
        results.append(("*", None, mod))

    elif node.type == "scoped_use_list":
        # e.g. crate::utils::{format_header, validate as val}
        path_node = node.child_by_field_name("path")
        list_node = node.child_by_field_name("list")
        new_prefix = _node_text(path_node, source) if path_node else ""
        if prefix:
            new_prefix = f"{prefix}::{new_prefix}" if new_prefix else prefix
        if list_node:
            for child in list_node.named_children:
                results.extend(_extract_use_clause(child, source, new_prefix))

    elif node.type == "use_list":
        # e.g. {format_header, validate as val}
        for child in node.named_children:
            results.extend(_extract_use_clause(child, source, prefix))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Call extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_calls_from_block(node: Node, source: bytes) -> List[ResolvedCall]:
    """
    Recursively walks a function body to extract call expressions.

    3-state model:
      exact      – cannot be proven exact at parser stage; upgraded by resolver
      inferred   – receiver is self (method call on self)
      unresolved – external or unknown receiver
    """
    calls: List[ResolvedCall] = []
    seen: Set[str] = set()

    def walk(n: Node):
        if n.type == "call_expression":
            func_node = n.child_by_field_name("function")
            if func_node:
                raw = _node_text(func_node, source)

                # Deduplicate to avoid listing the same call repeatedly
                if raw not in seen:
                    seen.add(raw)

                    if func_node.type == "identifier":
                        # bare call: validate(id) — inferred (could be local or imported)
                        calls.append(ResolvedCall(
                            raw_name=raw,
                            target_qualified_name=None,
                            resolution="inferred",
                            resolution_note="bare_local_call"
                        ))

                    elif func_node.type == "field_expression":
                        # method call: self.validate(id) or obj.method()
                        obj_node = func_node.child_by_field_name("value")
                        field_node = func_node.child_by_field_name("field")
                        obj_text = _node_text(obj_node, source) if obj_node else ""
                        field_text = _node_text(field_node, source) if field_node else raw
                        if obj_text == "self":
                            calls.append(ResolvedCall(
                                raw_name=raw,
                                target_qualified_name=None,
                                resolution="inferred",
                                resolution_note="self_method_call"
                            ))
                        else:
                            calls.append(ResolvedCall(
                                raw_name=raw,
                                target_qualified_name=None,
                                resolution="unresolved",
                                resolution_note="external_receiver_call"
                            ))

                    elif func_node.type == "scoped_identifier":
                        # Type::method() or module::func()
                        raw_scoped = _node_text(func_node, source)
                        calls.append(ResolvedCall(
                            raw_name=raw_scoped,
                            target_qualified_name=None,
                            resolution="unresolved",
                            resolution_note="scoped_call_needs_resolver"
                        ))

                    else:
                        calls.append(ResolvedCall(
                            raw_name=raw,
                            target_qualified_name=None,
                            resolution="unresolved",
                            resolution_note="unknown_call_form"
                        ))

        for child in n.children:
            walk(child)

    walk(node)
    return calls


# ─────────────────────────────────────────────────────────────────────────────
# Parameter extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_parameters(params_node: Optional[Node], source: bytes) -> List[ParsedParameter]:
    params: List[ParsedParameter] = []
    if not params_node:
        return params

    for child in params_node.named_children:
        if child.type == "parameter":
            name_node = child.child_by_field_name("pattern")
            type_node = child.child_by_field_name("type")
            name = _node_text(name_node, source) if name_node else ""
            type_ann = _node_text(type_node, source) if type_node else None
            if name and name not in ("self", "&self", "&mut self"):
                params.append(ParsedParameter(name=name, type_annotation=type_ann))
        elif child.type == "self_parameter":
            pass  # skip self receiver
        elif child.type in ("variadic_parameter",):
            params.append(ParsedParameter(name="...", type_annotation=None))

    return params


# ─────────────────────────────────────────────────────────────────────────────
# Axum route extraction (static only, no macro expansion)
# ─────────────────────────────────────────────────────────────────────────────

_AXUM_ROUTE_RE = re.compile(
    r'\.route\(\s*["\']([^"\']+)["\']\s*,\s*(get|post|put|delete|patch|options|head)\s*\(\s*([a-zA-Z0-9_]+)\s*\)',
    re.IGNORECASE
)
_ACTIX_ATTR_RE = re.compile(
    r'#\[\s*(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\]'
    r'\s*(?:pub\s+)?(?:async\s+)?fn\s+([a-zA-Z0-9_]+)',
    re.IGNORECASE
)
_ROCKET_ATTR_RE = _ACTIX_ATTR_RE  # Same attribute syntax


def _extract_rust_routes(pfile: ParsedFile, content: str, module_name: str) -> List[Dict]:
    """Extracts Axum, Actix Web, and Rocket route declarations from Rust source."""
    routes: List[Dict] = []
    if not content:
        return routes

    # Axum: Router::new().route("/path", get(handler))
    for m in _AXUM_ROUTE_RE.finditer(content):
        path, method, handler = m.group(1), m.group(2).upper(), m.group(3)
        handler_qname = f"{module_name}.{handler}"
        routes.append({
            "method": method,
            "path": path,
            "handler_qualified_name": handler_qname,
            "framework": "axum",
        })

    # Actix / Rocket: #[get("/path")] async fn handler()
    for m in _ACTIX_ATTR_RE.finditer(content):
        method, path, handler = m.group(1).upper(), m.group(2), m.group(3)
        handler_qname = f"{module_name}.{handler}"
        framework = "actix" if "actix" in content[:500].lower() else "rocket"
        routes.append({
            "method": method,
            "path": path,
            "handler_qualified_name": handler_qname,
            "framework": framework,
        })

    return routes


# ─────────────────────────────────────────────────────────────────────────────
# Main RustVisitor
# ─────────────────────────────────────────────────────────────────────────────

class RustVisitor:
    """
    Walks tree-sitter Rust AST to extract universal IR facts:
      - Module identity
      - use declarations (all forms)
      - mod declarations (file and inline)
      - Structs, enums, traits as ParsedClass entities
      - Top-level functions, async functions, impl methods
      - Function calls with strict 3-state model
      - Cyclomatic complexity & nesting depth
      - Doc comments
    """

    def __init__(self, source_bytes: bytes, file_path: str, module_name: str):
        self.source = source_bytes
        self.file_path = file_path
        self.module_name = module_name

        self.imports: List[ParsedImport] = []
        self.classes: List[ParsedClass] = []
        self.functions: List[ParsedFunction] = []
        self.file_docstring: Optional[str] = None
        self.parse_errors: List[str] = []

    def _text(self, node: Optional[Node]) -> str:
        return _node_text(node, self.source)

    # ── Entry point ────────────────────────────────────────────────────────────

    def visit(self, root: Node):
        # Collect pending attribute_items to attach to the next declaration
        pending_attrs: List[Node] = []

        # Pass 1: imports, mod declarations, types
        classes_by_name: Dict[str, ParsedClass] = {}

        for child in root.children:
            if child.type == "line_comment":
                raw = self._text(child)
                if raw.strip().startswith("//!") and not self.file_docstring:
                    self.file_docstring = _clean_rust_doc(raw)

            elif child.type == "inner_attribute_item":
                pass  # crate-level attributes, ignored

            elif child.type == "attribute_item":
                pending_attrs.append(child)

            elif child.type == "use_declaration":
                self._visit_use(child)
                pending_attrs.clear()

            elif child.type == "mod_item":
                self._visit_mod(child)
                pending_attrs.clear()

            elif child.type == "struct_item":
                doc = _get_preceding_doc(child, self.source)
                cls = self._visit_struct(child, doc)
                if cls:
                    classes_by_name[cls.name] = cls
                pending_attrs.clear()

            elif child.type == "enum_item":
                doc = _get_preceding_doc(child, self.source)
                cls = self._visit_enum(child, doc)
                if cls:
                    classes_by_name[cls.name] = cls
                pending_attrs.clear()

            elif child.type == "trait_item":
                doc = _get_preceding_doc(child, self.source)
                cls = self._visit_trait(child, doc)
                if cls:
                    classes_by_name[cls.name] = cls
                pending_attrs.clear()

            elif child.type == "union_item":
                doc = _get_preceding_doc(child, self.source)
                cls = self._visit_union(child, doc)
                if cls:
                    classes_by_name[cls.name] = cls
                pending_attrs.clear()

            elif child.type == "function_item":
                doc = _get_preceding_doc(child, self.source)
                func = self._visit_function(child, self.module_name, None, doc)
                if func:
                    self.functions.append(func)
                pending_attrs.clear()

            elif child.type == "impl_item":
                self._visit_impl(child, classes_by_name)
                pending_attrs.clear()

            else:
                pending_attrs.clear()

        self.classes = list(classes_by_name.values())

    # ── Use declarations ────────────────────────────────────────────────────────

    def _visit_use(self, node: Node):
        """Processes a use_declaration into ParsedImport records."""
        # Find the 'argument' child (the path/list)
        arg = None
        for child in node.named_children:
            if child.type not in ("visibility_modifier",):
                arg = child
                break

        if not arg:
            return

        items = _extract_use_clause(arg, self.source, "")
        for (name, alias, module_path) in items:
            self.imports.append(ParsedImport(
                name=name,
                alias=alias,
                is_from_import=bool(module_path),
                module=module_path if module_path else None,
            ))

    # ── Mod declarations ────────────────────────────────────────────────────────

    def _visit_mod(self, node: Node):
        """
        Handles mod declarations:
          mod helper;          -> ParsedImport representing file-level module reference
          mod inline_mod {...} -> inline module (functions extracted as sub-functions)
        """
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")

        if not name_node:
            return

        mod_name = self._text(name_node)

        if body_node is None:
            # mod helper; — refers to helper.rs or helper/mod.rs
            self.imports.append(ParsedImport(
                name=mod_name,
                alias=None,
                is_from_import=False,
                module=f"./{mod_name}",  # Relative mod reference, resolved by ML-9 resolver
            ))
        # Inline mods: functions inside are extracted separately
        # For now, we do not recurse into inline mods to keep impl simple.
        # They would need their own qualified name scoping.

    # ── Structs ─────────────────────────────────────────────────────────────────

    def _visit_struct(self, node: Node, doc: Optional[str]) -> Optional[ParsedClass]:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = self._text(name_node)
        qname = f"{self.module_name}.{name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        return ParsedClass(
            name=name,
            qualified_name=qname,
            base_classes=[],
            methods=[],
            start_line=start_line,
            end_line=end_line,
            line_count=max(1, end_line - start_line + 1),
            docstring=doc,
        )

    # ── Enums ───────────────────────────────────────────────────────────────────

    def _visit_enum(self, node: Node, doc: Optional[str]) -> Optional[ParsedClass]:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = self._text(name_node)
        qname = f"{self.module_name}.{name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        return ParsedClass(
            name=name,
            qualified_name=qname,
            base_classes=[],
            methods=[],
            start_line=start_line,
            end_line=end_line,
            line_count=max(1, end_line - start_line + 1),
            docstring=doc,
        )

    # ── Traits ──────────────────────────────────────────────────────────────────

    def _visit_trait(self, node: Node, doc: Optional[str]) -> Optional[ParsedClass]:
        """
        Traits are represented as ParsedClass with is_from_import=False.
        Trait method signatures (function_signature_item) are extracted as zero-body
        ParsedFunction with is_method=True.
        """
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = self._text(name_node)
        qname = f"{self.module_name}.{name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Supertrait names -> base_classes
        base_classes: List[str] = []
        bounds_node = node.child_by_field_name("bounds")
        if bounds_node:
            for b in bounds_node.named_children:
                b_text = self._text(b).strip()
                if b_text:
                    base_classes.append(b_text)

        # Extract trait method signatures
        methods: List[ParsedFunction] = []
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.named_children:
                if child.type in ("function_item", "function_signature_item"):
                    m = self._visit_function(child, qname, qname, None)
                    if m:
                        methods.append(m)

        return ParsedClass(
            name=name,
            qualified_name=qname,
            base_classes=base_classes,
            methods=methods,
            start_line=start_line,
            end_line=end_line,
            line_count=max(1, end_line - start_line + 1),
            docstring=doc,
        )

    # ── Unions ──────────────────────────────────────────────────────────────────

    def _visit_union(self, node: Node, doc: Optional[str]) -> Optional[ParsedClass]:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = self._text(name_node)
        qname = f"{self.module_name}.{name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        return ParsedClass(
            name=name,
            qualified_name=qname,
            base_classes=[],
            methods=[],
            start_line=start_line,
            end_line=end_line,
            line_count=max(1, end_line - start_line + 1),
            docstring=doc,
        )

    # ── Functions ───────────────────────────────────────────────────────────────

    def _visit_function(
        self,
        node: Node,
        module_name: str,
        owner_qname: Optional[str],
        doc: Optional[str],
    ) -> Optional[ParsedFunction]:
        """Extracts a function_item or function_signature_item into a ParsedFunction."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        func_name = self._text(name_node)

        if owner_qname:
            qname = f"{owner_qname}.{func_name}"
        else:
            qname = f"{module_name}.{func_name}"

        # Parameters
        params_node = node.child_by_field_name("parameters")
        params = _extract_parameters(params_node, self.source)

        # Return type
        ret_node = node.child_by_field_name("return_type")
        return_annotation = self._text(ret_node).strip("-> ").strip() if ret_node else None

        # Is async? function_modifiers is a named child but has NO field name in
        # tree-sitter-rust 0.24; child_by_field_name("function_modifiers") returns None.
        # Scan children by node type instead.
        is_async = False
        for child in node.children:
            if child.type == "function_modifiers":
                mods_text = self._text(child)
                is_async = "async" in mods_text
                break
            if child.type == "fn":
                break  # Past modifier area — no modifiers found

        # Is method (has self receiver)?
        is_method = owner_qname is not None
        if params_node:
            for child in params_node.named_children:
                if child.type == "self_parameter":
                    is_method = True
                    break

        # Body
        body_node = node.child_by_field_name("body")
        calls: List[ResolvedCall] = []
        complexity = 1
        nesting = 0
        if body_node:
            calls = _extract_calls_from_block(body_node, self.source)
            complexity = _compute_complexity(body_node)
            nesting = _compute_nesting(body_node)

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        return ParsedFunction(
            name=func_name,
            qualified_name=qname,
            parameters=params,
            decorators=[],
            return_annotation=return_annotation,
            is_method=is_method,
            is_async=is_async,
            cyclomatic_complexity=complexity,
            nesting_depth=nesting,
            start_line=start_line,
            end_line=end_line,
            line_count=max(1, end_line - start_line + 1),
            docstring=doc,
            calls=calls,
        )

    # ── Impl blocks ─────────────────────────────────────────────────────────────

    def _visit_impl(self, node: Node, classes_by_name: Dict[str, ParsedClass]):
        """
        Processes impl blocks:
          - impl Foo { ... }                   -> inherent impl; methods attached to Foo
          - impl Trait for Foo { ... }         -> trait impl; methods also attached to Foo

        In both cases, methods are attributed to the implementing type (Foo) for
        consistent graph topology. The trait relationship is not discarded but is
        not fabricated as a new class node.
        """
        # Determine the implementing type name
        # tree-sitter node structure for impl:
        #   impl TypeName { ... }
        #   impl TraitName for TypeName { ... }
        type_nodes: List[Node] = []
        for child in node.named_children:
            if child.type == "type_identifier":
                type_nodes.append(child)

        if not type_nodes:
            return

        # For "impl Trait for Type": last type_identifier is the implementing type
        implementing_type_node = type_nodes[-1]
        implementing_type = self._text(implementing_type_node)

        # Get or create ParsedClass for implementing type
        if implementing_type not in classes_by_name:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            classes_by_name[implementing_type] = ParsedClass(
                name=implementing_type,
                qualified_name=f"{self.module_name}.{implementing_type}",
                base_classes=[],
                methods=[],
                start_line=start_line,
                end_line=end_line,
                line_count=max(1, end_line - start_line + 1),
                docstring=None,
            )

        cls = classes_by_name[implementing_type]
        owner_qname = cls.qualified_name

        # If it's a trait impl, record the trait as a base_class
        if len(type_nodes) >= 2:
            trait_name = self._text(type_nodes[0])
            if trait_name not in cls.base_classes:
                cls.base_classes.append(trait_name)

        # Extract methods
        body_node = node.child_by_field_name("body")
        if not body_node:
            return

        for child in body_node.named_children:
            if child.type == "function_item":
                doc = _get_preceding_doc(child, self.source)
                func = self._visit_function(child, self.module_name, owner_qname, doc)
                if func:
                    cls.methods.append(func)


# ─────────────────────────────────────────────────────────────────────────────
# Main LanguageParser implementation
# ─────────────────────────────────────────────────────────────────────────────

class RustParser(LanguageParser):
    """
    Production Rust parser for Archon's language-neutral pipeline (Slice ML-9).

    Handles .rs files. Never executes Rust code or Cargo.
    """

    _parser = Parser(RUST_LANG)

    @property
    def language(self) -> str:
        return "rust"

    @property
    def file_extensions(self) -> List[str]:
        return [".rs"]

    def parse_file(self, path: str, content: str) -> ParsedFile:
        """
        Parse Rust source into universal IR.
        Never raises. All errors appended to parse_errors.
        """
        errors: List[str] = []

        # Derive module name
        try:
            crate_name = _read_cargo_package_name(path)
            module_name = _derive_rust_module_name(path, crate_name)
        except Exception as e:
            module_name = Path(path).stem
            errors.append(f"module_name_derivation_error: {e}")

        source_bytes = content.encode("utf-8", errors="replace")
        total_lines = content.count("\n") + 1

        try:
            tree = self._parser.parse(source_bytes)

            if tree.root_node.has_error:
                errors.append("tree_sitter_parse_error: AST contains error nodes")

            visitor = RustVisitor(source_bytes, path, module_name)
            visitor.visit(tree.root_node)

            imports = visitor.imports
            classes = visitor.classes
            functions = visitor.functions
            file_docstring = visitor.file_docstring
            errors.extend(visitor.parse_errors)

        except Exception as e:
            logger.warning("rust_parse_failed", path=path, error=str(e))
            errors.append(f"fatal_parse_error: {e}")
            imports, classes, functions = [], [], []
            file_docstring = None

        return ParsedFile(
            path=path,
            language="rust",
            module_name=module_name,
            total_lines=total_lines,
            docstring=file_docstring,
            classes=classes,
            functions=functions,
            imports=imports,
            parse_errors=errors,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Self-register at import time
# ─────────────────────────────────────────────────────────────────────────────

registry.register(RustParser())
