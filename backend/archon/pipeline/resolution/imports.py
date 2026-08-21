"""
Canonical Module & Symbol Import Resolution Engine (Slice ML-8)

Performs deterministic, snapshot-scoped, cross-file and cross-language symbol
and module resolution across Python, TypeScript, JavaScript, Java, C#, and Go.
"""

import posixpath
import re
from typing import List, Dict, Optional, Set, Tuple, Any
import structlog

from archon.pipeline.parsers.base import (
    ParsedFile,
    ParsedFunction,
    ParsedClass,
    ParsedImport,
)
from archon.pipeline.parsers.registry import registry
import archon.pipeline.parsers.python.parser  # Auto-register
import archon.pipeline.parsers.typescript.parser  # Auto-register
import archon.pipeline.parsers.javascript.parser  # Auto-register
import archon.pipeline.parsers.java.parser  # Auto-register
import archon.pipeline.parsers.csharp.parser  # Auto-register
import archon.pipeline.parsers.go.parser  # Auto-register
import archon.pipeline.parsers.rust.parser  # Auto-register

from archon.pipeline.resolution.base import BaseResolver
from archon.pipeline.resolution.models import ResolutionResult

logger = structlog.get_logger(__name__)

DEFAULT_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".java", ".cs", ".go", ".rs"]

MAX_ALIAS_DEPTH = 5
MAX_REEXPORT_DEPTH = 5


def _normalize_repo_path(path: str) -> str:
    """Normalize path to forward slashes with no leading ./ or /."""
    p = path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    if p.startswith("/"):
        p = p[1:]
    return p


class ModuleSymbolIndex:
    """
    Deterministic, snapshot-scoped index of all modules, files, exports,
    and addressable symbols across all languages in a repository.
    """

    def __init__(self, parsed_files: List[ParsedFile], file_contents: Optional[Dict[str, str]] = None):
        self.parsed_files = parsed_files
        self.file_contents = file_contents or {}

        # 1. Path & Module lookups
        self.file_by_path: Dict[str, ParsedFile] = {}
        self.module_by_name: Dict[str, ParsedFile] = {}
        self.files_by_dir: Dict[str, List[ParsedFile]] = {}

        # 2. Symbols per file
        self.symbols_by_file: Dict[str, Dict[str, str]] = {}
        self.functions_by_file: Dict[str, Dict[str, ParsedFunction]] = {}
        self.classes_by_file: Dict[str, Dict[str, ParsedClass]] = {}

        # 3. Local aliases per file: { norm_path: { alias_name: target_name } }
        self.local_aliases_by_file: Dict[str, Dict[str, str]] = {}

        self.supported_exts = sorted(set(registry.supported_extensions()) | set(DEFAULT_EXTENSIONS))
        self._build_index()

    def _build_index(self):
        """Indexes all files, module identities, functions, classes, and local aliases."""
        for pfile in self.parsed_files:
            norm_path = _normalize_repo_path(pfile.path)
            self.file_by_path[norm_path] = pfile

            if pfile.module_name:
                self.module_by_name[pfile.module_name] = pfile

            parent_dir = posixpath.dirname(norm_path)
            self.files_by_dir.setdefault(parent_dir, []).append(pfile)

            # Index symbols for this file
            file_symbols: Dict[str, str] = {}
            file_funcs: Dict[str, ParsedFunction] = {}
            file_classes: Dict[str, ParsedClass] = {}

            # Top-level functions
            for func in pfile.functions:
                file_symbols[func.name] = func.qualified_name
                file_funcs[func.name] = func

            # Classes and class methods
            for cls in pfile.classes:
                file_symbols[cls.name] = cls.qualified_name
                file_classes[cls.name] = cls
                for method in cls.methods:
                    # e.g. Class.method or method name
                    file_symbols[f"{cls.name}.{method.name}"] = method.qualified_name
                    if method.name not in file_symbols:
                        file_symbols[method.name] = method.qualified_name
                    file_funcs[method.name] = method
                    file_funcs[f"{cls.name}.{method.name}"] = method

            self.symbols_by_file[norm_path] = file_symbols
            self.functions_by_file[norm_path] = file_funcs
            self.classes_by_file[norm_path] = file_classes

            # Extract local aliases
            content = self.file_contents.get(pfile.path)
            self.local_aliases_by_file[norm_path] = self._extract_local_aliases(pfile, content)

    def _extract_local_aliases(self, pfile: ParsedFile, content: Optional[str]) -> Dict[str, str]:
        """Statically extracts local variable identifier aliases (e.g. const b = a; b = a)."""
        aliases: Dict[str, str] = {}
        if not content:
            return aliases

        # Simple fast regex extraction for variable aliases: const/let/var b = a; or b = a
        # 1. JS / TS: const b = a; let b = a; var b = a;
        if pfile.language in ("javascript", "typescript"):
            for m in re.finditer(r'(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*[;\n]', content):
                aliases[m.group(1)] = m.group(2)

        # 2. Python: b = a
        elif pfile.language == "python":
            for m in re.finditer(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*$', content, re.MULTILINE):
                aliases[m.group(1)] = m.group(2)

        # 3. Go: b := a
        elif pfile.language == "go":
            for m in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:=\s*([a-zA-Z_][a-zA-Z0-9_]*)', content):
                aliases[m.group(1)] = m.group(2)

        # 4. C#: var b = a;
        elif pfile.language == "csharp":
            for m in re.finditer(r'var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*;', content):
                aliases[m.group(1)] = m.group(2)

        # 5. Rust: let b = a;
        elif pfile.language == "rust":
            for m in re.finditer(r'let(?:\s+mut)?\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*[;\n]', content):
                aliases[m.group(1)] = m.group(2)

        return aliases

    def resolve_alias(self, file_path: str, name: str, max_depth: int = MAX_ALIAS_DEPTH) -> str:
        """Resolves local identifier alias chains to the canonical name with cycle detection."""
        norm_path = _normalize_repo_path(file_path)
        alias_map = self.local_aliases_by_file.get(norm_path, {})
        curr = name
        visited = set()
        depth = 0

        while curr in alias_map and depth < max_depth:
            if curr in visited:
                break
            visited.add(curr)
            curr = alias_map[curr]
            depth += 1

        return curr


class ModuleAndSymbolResolver(BaseResolver):
    """
    Comprehensive cross-file & cross-language module and symbol resolver (Slice ML-8).
    Resolves:
      1. Explicit named imports & aliases
      2. Namespace & default imports
      3. Barrel & index module re-exports
      4. Multi-hop local aliases
      5. Cross-language imports (TS -> JS, JS -> TS, etc.)
      6. Upgrades function calls to exact destination function qualified names.
    """

    def resolve(
        self,
        parsed_files: List[ParsedFile],
        file_contents: Optional[Dict[str, str]] = None
    ) -> List[ResolutionResult]:
        index = ModuleSymbolIndex(parsed_files, file_contents)
        results: List[ResolutionResult] = []

        # Track already emitted edges to guarantee idempotency
        emitted_keys: Set[Tuple[str, str, str]] = set()

        for source_pfile in parsed_files:
            source_norm_path = _normalize_repo_path(source_pfile.path)
            source_module = source_pfile.module_name or source_norm_path

            # 1. Resolve Module Imports
            for imp in source_pfile.imports:
                if not imp.module:
                    continue

                target_pfile, evidence_type = self._resolve_module(source_pfile, imp, index)

                if target_pfile is not None:
                    target_module = target_pfile.module_name or target_pfile.path
                    edge_key = (source_module, target_module, "IMPORTS")

                    if edge_key not in emitted_keys:
                        emitted_keys.add(edge_key)
                        results.append(ResolutionResult(
                            source_id=source_module,
                            target_id=target_module,
                            relationship="IMPORTS",
                            resolution="exact",
                            evidence_type=evidence_type,
                            reason=f"Import '{imp.module}' uniquely resolved to repository file '{target_pfile.path}'",
                            source_language=source_pfile.language,
                            target_language=target_pfile.language,
                            source_file=source_pfile.path,
                            target_file=target_pfile.path
                        ))

            # 2. Resolve Function Calls -> Exact Destination Function
            source_functions: List[ParsedFunction] = list(source_pfile.functions)
            for cls in source_pfile.classes:
                source_functions.extend(cls.methods)

            for src_func in source_functions:
                for call in src_func.calls:
                    call_results = self._resolve_call_to_exact_symbol(
                        source_pfile=source_pfile,
                        src_func=src_func,
                        call=call,
                        index=index
                    )
                    for res in call_results:
                        call_key = (res.source_id, res.target_id, res.relationship)
                        if call_key not in emitted_keys:
                            emitted_keys.add(call_key)
                            results.append(res)

        logger.info(
            "symbol_and_module_resolution_complete",
            total_resolved=len(results),
            exact_count=sum(1 for r in results if r.resolution == "exact"),
            imports_count=sum(1 for r in results if r.relationship == "IMPORTS"),
            calls_count=sum(1 for r in results if r.relationship == "CALLS")
        )
        return results

    def _resolve_module(
        self,
        source_pfile: ParsedFile,
        imp: ParsedImport,
        index: ModuleSymbolIndex
    ) -> Tuple[Optional[ParsedFile], str]:
        """Resolves an import declaration to a unique repository file."""
        if not imp.module:
            return None, "unresolved"

        source_norm_path = _normalize_repo_path(source_pfile.path)
        source_dir = posixpath.dirname(source_norm_path)

        # ── 1. TypeScript & JavaScript ────────────────────────────────────────
        if source_pfile.language in ("javascript", "typescript"):
            return self._resolve_js_ts_module(source_dir, imp.module, index)

        # ── 2. Python ─────────────────────────────────────────────────────────
        elif source_pfile.language == "python":
            return self._resolve_python_module(source_norm_path, imp, index)

        # ── 3. Java ───────────────────────────────────────────────────────────
        elif source_pfile.language == "java":
            return self._resolve_java_module(imp, index)

        # ── 4. C# ─────────────────────────────────────────────────────────────
        elif source_pfile.language == "csharp":
            return self._resolve_csharp_module(imp, index)

        # ── 5. Go ──────────────────────────────────────────────────────────────
        elif source_pfile.language == "go":
            return self._resolve_go_module(imp, index)

        # ── 6. Rust ────────────────────────────────────────────────────────────
        elif source_pfile.language == "rust":
            return self._resolve_rust_module(source_pfile, imp, index)

        return None, "unresolved"

    def _resolve_js_ts_module(
        self,
        source_dir: str,
        import_path: str,
        index: ModuleSymbolIndex
    ) -> Tuple[Optional[ParsedFile], str]:
        """Resolves JS/TS relative imports with extensionless & index resolution."""
        if not import_path.startswith("."):
            return None, "external_or_package"

        # Confinement check
        target_base = posixpath.normpath(posixpath.join(source_dir, import_path))
        if target_base.startswith("..") or target_base.startswith("/"):
            return None, "path_escape_prevented"

        candidates: Set[str] = set()

        # Direct path (if explicit extension provided)
        if target_base in index.file_by_path:
            candidates.add(target_base)

        # Extensionless candidates
        for ext in index.supported_exts:
            cand = f"{target_base}{ext}"
            if cand in index.file_by_path:
                candidates.add(cand)

        # Directory index candidates (barrel modules)
        for ext in index.supported_exts:
            cand = f"{target_base}/index{ext}"
            if cand in index.file_by_path:
                candidates.add(cand)

        if len(candidates) == 1:
            matched_path = next(iter(candidates))
            evidence = "directory_index" if "/index." in matched_path else "relative_import"
            return index.file_by_path[matched_path], evidence

        return None, "ambiguous_or_missing"

    def _resolve_python_module(
        self,
        source_norm_path: str,
        imp: ParsedImport,
        index: ModuleSymbolIndex
    ) -> Tuple[Optional[ParsedFile], str]:
        """Resolves Python relative and absolute module imports."""
        if not imp.module:
            return None, "unresolved"

        # Relative import e.g. from .utils import x or from ..core.engine import y
        if imp.is_from_import and imp.module.startswith("."):
            source_dir = posixpath.dirname(source_norm_path)
            dot_count = 0
            for char in imp.module:
                if char == ".":
                    dot_count += 1
                else:
                    break

            sub_path = imp.module[dot_count:].replace(".", "/")
            current_dir = source_dir
            for _ in range(dot_count - 1):
                current_dir = posixpath.dirname(current_dir)

            target_base = posixpath.normpath(posixpath.join(current_dir, sub_path)) if sub_path else current_dir
            if target_base.startswith("..") or target_base.startswith("/"):
                return None, "path_escape_prevented"

            cand = f"{target_base}.py"
            if cand in index.file_by_path:
                return index.file_by_path[cand], "python_relative_import"

            init_cand = f"{target_base}/__init__.py"
            if init_cand in index.file_by_path:
                return index.file_by_path[init_cand], "python_relative_import"

            return None, "unresolved"

        # Absolute import e.g. services.auth
        if imp.module in index.module_by_name:
            return index.module_by_name[imp.module], "python_absolute_import"

        as_path = imp.module.replace(".", "/") + ".py"
        if as_path in index.file_by_path:
            return index.file_by_path[as_path], "python_absolute_import"

        init_path = imp.module.replace(".", "/") + "/__init__.py"
        if init_path in index.file_by_path:
            return index.file_by_path[init_path], "python_absolute_import"

        return None, "external_or_stdlib"

    def _resolve_java_module(
        self,
        imp: ParsedImport,
        index: ModuleSymbolIndex
    ) -> Tuple[Optional[ParsedFile], str]:
        """Resolves Java package or class imports."""
        if not imp.module and not imp.name:
            return None, "unresolved"

        full_qname = f"{imp.module}.{imp.name}" if imp.module else imp.name

        # Direct class match: com.example.services.PaymentService -> com/example/services/PaymentService.java
        as_path = full_qname.replace(".", "/") + ".java"
        if as_path in index.file_by_path:
            return index.file_by_path[as_path], "java_class_import"

        if full_qname in index.module_by_name:
            return index.module_by_name[full_qname], "java_class_import"

        # Static import: com.example.utils.Formatter.formatHeaders -> com/example/utils/Formatter.java
        if imp.module:
            mod_as_path = imp.module.replace(".", "/") + ".java"
            if mod_as_path in index.file_by_path:
                return index.file_by_path[mod_as_path], "java_static_import"

        return None, "external_package"

    def _resolve_csharp_module(
        self,
        imp: ParsedImport,
        index: ModuleSymbolIndex
    ) -> Tuple[Optional[ParsedFile], str]:
        """Resolves C# namespace or type usings."""
        target_name = f"{imp.module}.{imp.name}" if imp.module else imp.name

        # Match exact module name or class
        if target_name in index.module_by_name:
            return index.module_by_name[target_name], "csharp_using"

        as_path = target_name.replace(".", "/") + ".cs"
        if as_path in index.file_by_path:
            return index.file_by_path[as_path], "csharp_using"

        # Check if any file has matching namespace
        for pfile in index.parsed_files:
            if pfile.language == "csharp" and pfile.module_name and (
                pfile.module_name == target_name or pfile.module_name.startswith(f"{target_name}.")
            ):
                return pfile, "csharp_namespace_using"

        return None, "external_namespace"

    def _resolve_go_module(
        self,
        imp: ParsedImport,
        index: ModuleSymbolIndex
    ) -> Tuple[Optional[ParsedFile], str]:
        """Resolves Go repository-local package imports."""
        target_path = f"{imp.module}/{imp.name}" if imp.module else imp.name

        # Look for directory matching package path in repository
        for pdir, files in index.files_by_dir.items():
            if pdir.endswith(target_path) or pdir.endswith(imp.name):
                go_files = [f for f in files if f.language == "go"]
                if go_files:
                    return go_files[0], "go_package_import"

        return None, "external_package"

    def _resolve_rust_module(
        self,
        source_pfile: ParsedFile,
        imp: ParsedImport,
        index: ModuleSymbolIndex,
    ) -> Tuple[Optional[ParsedFile], str]:
        """
        Resolves Rust use declarations and mod references to repository-local files.

        Handles:
          crate::path::to::module  -> src/path/to/module.rs or src/path/to/module/mod.rs
          self::path::to::module   -> <source_dir>/path/to/module.rs
          super::path::to::module  -> <parent_dir>/path/to/module.rs
          ./mod_name               -> mod_name.rs or mod_name/mod.rs (mod declarations)

        External crates (no crate::, self::, super:: prefix, not relative) -> unresolved.
        """
        if not imp.module:
            return None, "unresolved"

        source_norm_path = _normalize_repo_path(source_pfile.path)
        source_dir = posixpath.dirname(source_norm_path)

        # Find crate root: walk up to find src/ ancestor
        def _find_crate_src(path_parts: List[str]) -> str:
            for i in range(len(path_parts) - 1, -1, -1):
                if path_parts[i] == "src":
                    return "/".join(path_parts[:i + 1])
            return source_dir

        source_parts = source_norm_path.split("/")
        crate_src_root = _find_crate_src(source_parts)

        def _candidates(base: str) -> List[str]:
            """Return candidate file paths for a base module path."""
            norm_base = posixpath.normpath(base)
            if norm_base.startswith("..") or norm_base.startswith("/"):
                return []
            return [f"{norm_base}.rs", f"{norm_base}/mod.rs"]

        def _lookup(candidates: List[str]) -> Tuple[Optional[ParsedFile], str]:
            for cand in candidates:
                if cand in index.file_by_path:
                    return index.file_by_path[cand], "rust_module_import"
            return None, "unresolved"

        mod_path = imp.module

        # 1. crate:: — resolve from src root
        if mod_path.startswith("crate::"):
            sub = mod_path[len("crate::"):].replace("::", "/")
            base = posixpath.join(crate_src_root, sub)
            return _lookup(_candidates(base))

        # 2. self:: — resolve from current file's directory
        elif mod_path.startswith("self::"):
            sub = mod_path[len("self::"):].replace("::", "/")
            base = posixpath.join(source_dir, sub)
            return _lookup(_candidates(base))

        # 3. super:: — resolve from parent directory
        elif mod_path.startswith("super::"):
            sub = mod_path[len("super::"):].replace("::", "/")
            parent_dir = posixpath.dirname(source_dir)
            base = posixpath.join(parent_dir, sub)
            return _lookup(_candidates(base))

        # 4. mod declaration reference (./<mod_name>)
        elif mod_path.startswith("./") or mod_path.startswith("../"):
            sub = mod_path.lstrip("./").replace("::", "/")
            base = posixpath.join(source_dir, sub)
            return _lookup(_candidates(base))

        # 5. Pure crate name or unqualified external crate -> unresolved
        return None, "external_crate"

    def _resolve_symbol_in_target(
        self,
        target_pfile: ParsedFile,
        symbol_name: str,
        index: ModuleSymbolIndex,
        depth: int = 0,
        visited: Optional[Set[Tuple[str, str]]] = None
    ) -> Optional[Tuple[str, str, ParsedFile]]:
        """
        Recursively resolves symbol in target module, traversing barrel / re-export chains
        with bounded depth and cycle detection.
        Returns: (target_qualified_name, evidence_type, final_target_pfile)
        """
        if visited is None:
            visited = set()

        visit_key = (target_pfile.path, symbol_name)
        if visit_key in visited or depth >= MAX_REEXPORT_DEPTH:
            return None
        visited.add(visit_key)

        target_norm_path = _normalize_repo_path(target_pfile.path)
        symbols = index.symbols_by_file.get(target_norm_path, {})

        # 1. Base Case: symbol directly defined in this file
        if symbol_name in symbols:
            evidence = "reexport_symbol" if depth > 0 else "explicit_import_symbol"
            return symbols[symbol_name], evidence, target_pfile

        # 2. Recursive Case: traverse re-exports in target_pfile
        for imp in target_pfile.imports:
            if not imp.module:
                continue

            is_match = (
                imp.name == symbol_name or
                imp.alias == symbol_name or
                imp.name == "*" or
                imp.name == ""
            )

            if is_match:
                next_target, _ = self._resolve_module(target_pfile, imp, index)
                if next_target is not None:
                    lookup_name = symbol_name
                    if imp.name and imp.name != "*" and imp.alias == symbol_name:
                        lookup_name = imp.name

                    sub_res = self._resolve_symbol_in_target(
                        next_target,
                        lookup_name,
                        index,
                        depth=depth + 1,
                        visited=visited
                    )
                    if sub_res is not None:
                        return sub_res

        return None

    def _resolve_call_to_exact_symbol(
        self,
        source_pfile: ParsedFile,
        src_func: ParsedFunction,
        call: Any,
        index: ModuleSymbolIndex
    ) -> List[ResolutionResult]:
        """Attempts to upgrade a call to an exact destination Function qualified name."""
        results: List[ResolutionResult] = []
        raw_call_name = call.raw_name

        # 1. Resolve multi-hop local alias chain (e.g. aliasB -> aliasA -> fh)
        effective_name = index.resolve_alias(source_pfile.path, raw_call_name)

        # 2. Check each import in source file
        for imp in source_pfile.imports:
            target_pfile, _ = self._resolve_module(source_pfile, imp, index)
            if not target_pfile:
                continue

            # ── Case A: Named Import ──────────────────────────────────────────
            # e.g. import { formatHeaders as fh } from './formatter' -> call fh()
            local_imported_name = imp.alias if imp.alias else imp.name
            if local_imported_name and effective_name == local_imported_name:
                resolved = self._resolve_symbol_in_target(
                    target_pfile=target_pfile,
                    symbol_name=imp.name,
                    index=index
                )
                if resolved:
                    target_qname, evidence_type, final_file = resolved
                    results.append(ResolutionResult(
                        source_id=src_func.qualified_name,
                        target_id=target_qname,
                        relationship="CALLS",
                        resolution="exact",
                        evidence_type=evidence_type,
                        reason=f"Call '{raw_call_name}' in '{src_func.name}' uniquely resolves to '{target_qname}' in '{final_file.path}'",
                        source_language=source_pfile.language,
                        target_language=final_file.language,
                        source_file=source_pfile.path,
                        target_file=final_file.path
                    ))
                    return results

            # ── Case B: Namespace / Default / CommonJS Import ─────────────────
            # e.g. import * as utils from './utils' -> utils.formatHeaders()
            # or const formatter = require('./formatter') -> formatter.formatHeaders()
            elif imp.alias and not imp.is_from_import:
                resolved = self._resolve_symbol_in_target(
                    target_pfile=target_pfile,
                    symbol_name=effective_name,
                    index=index
                )
                if resolved:
                    target_qname, evidence_type, final_file = resolved
                    results.append(ResolutionResult(
                        source_id=src_func.qualified_name,
                        target_id=target_qname,
                        relationship="CALLS",
                        resolution="exact",
                        evidence_type="namespace_import_symbol",
                        reason=f"Namespace call '{raw_call_name}' in '{src_func.name}' uniquely resolves to '{target_qname}' in '{final_file.path}'",
                        source_language=source_pfile.language,
                        target_language=final_file.language,
                        source_file=source_pfile.path,
                        target_file=final_file.path
                    ))
                    return results

            # ── Case C: Java Static Import or C# Static Using ─────────────────
            # e.g. import static com.example.Utils.formatHeaders;
            elif imp.name and effective_name == imp.name:
                resolved = self._resolve_symbol_in_target(
                    target_pfile=target_pfile,
                    symbol_name=imp.name,
                    index=index
                )
                if resolved:
                    target_qname, evidence_type, final_file = resolved
                    results.append(ResolutionResult(
                        source_id=src_func.qualified_name,
                        target_id=target_qname,
                        relationship="CALLS",
                        resolution="exact",
                        evidence_type="static_import_symbol",
                        reason=f"Static call '{raw_call_name}' in '{src_func.name}' uniquely resolves to '{target_qname}' in '{final_file.path}'",
                        source_language=source_pfile.language,
                        target_language=final_file.language,
                        source_file=source_pfile.path,
                        target_file=final_file.path
                    ))
                    return results

            # ── Case D: Go Package Call ───────────────────────────────────────
            # e.g. import "myrepo/pkg/utils" -> utils.FormatHeaders()
            elif source_pfile.language == "go":
                resolved = self._resolve_symbol_in_target(
                    target_pfile=target_pfile,
                    symbol_name=effective_name,
                    index=index
                )
                if resolved:
                    target_qname, evidence_type, final_file = resolved
                    results.append(ResolutionResult(
                        source_id=src_func.qualified_name,
                        target_id=target_qname,
                        relationship="CALLS",
                        resolution="exact",
                        evidence_type="package_import_symbol",
                        reason=f"Go package call '{raw_call_name}' in '{src_func.name}' uniquely resolves to '{target_qname}' in '{final_file.path}'",
                        source_language=source_pfile.language,
                        target_language=final_file.language,
                        source_file=source_pfile.path,
                        target_file=final_file.path
                    ))
                    return results

        return results
