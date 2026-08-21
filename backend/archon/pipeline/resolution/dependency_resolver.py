"""
Dependency-Aware Call & Architecture Resolver (Slice ML-10)

Performs deterministic, repository-wide:
  1. Constructor & factory dependency edge emission (DEPENDS_ON)
  2. Interface & trait implementation edge emission (IMPLEMENTS)
  3. Static and class method call resolution (ClassName.method())
  4. Local receiver type tracking (var service = new Service(); service.charge())
  5. Injected field dependency call resolution (self.repo.save())
  6. DI container binding traversal (interface -> concrete implementation)
"""

import re
from typing import List, Dict, Optional, Set, Tuple, Any
import structlog

from archon.pipeline.parsers.base import (
    ParsedFile,
    ParsedFunction,
    ParsedClass,
)
from archon.pipeline.resolution.base import BaseResolver
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.resolution.imports import ModuleSymbolIndex, _normalize_repo_path
from archon.pipeline.resolution.type_index import RepositoryTypeIndex, TypeFact, DependencyFact

logger = structlog.get_logger(__name__)

MAX_LOCAL_TYPE_ALIAS_DEPTH = 5
MAX_RECEIVER_RESOLUTION_DEPTH = 5


class DependencyAwareCallResolver(BaseResolver):
    """
    Upgrades syntax-level calls to exact qualified method calls using
    statically proven receiver types, constructor dependencies, and DI bindings.
    """

    # Regex patterns for local variable instantiation / typing
    _NEW_INST_RE = re.compile(
        r'(?:const|let|var|final)?\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?::\s*([a-zA-Z0-9_]+))?\s*=\s*new\s+([a-zA-Z0-9_]+)\s*\(',
    )
    _PYTHON_INST_RE = re.compile(
        r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?::\s*([a-zA-Z0-9_]+))?\s*=\s*([A-Z][a-zA-Z0-9_]*)\s*\(',
        re.MULTILINE
    )
    _JAVA_CSHARP_TYPED_VAR_RE = re.compile(
        r'\b([A-Z][a-zA-Z0-9_]*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*new\s+([A-Z][a-zA-Z0-9_]*)\s*\(',
    )
    _GO_INST_RE = re.compile(
        r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:=\s*(?:New([A-Z][a-zA-Z0-9_]*)|&([A-Z][a-zA-Z0-9_]*)\s*\{)',
    )
    _RUST_INST_RE = re.compile(
        r'let(?:\s+mut)?\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?::\s*([a-zA-Z0-9_]+))?\s*=\s*([A-Z][a-zA-Z0-9_]*)::new\s*\(',
    )

    _MEMBER_CALL_RE = re.compile(
        r'\b([a-zA-Z_$][a-zA-Z0-9_$.]*)\s*(?:\.|\:\:)\s*([a-zA-Z0-9_$]+)\s*\(',
    )

    def resolve(
        self,
        parsed_files: List[ParsedFile],
        file_contents: Optional[Dict[str, str]] = None
    ) -> List[ResolutionResult]:
        contents = file_contents or {}
        type_index = RepositoryTypeIndex(parsed_files, contents)
        results: List[ResolutionResult] = []
        emitted_keys: Set[Tuple[str, str, str]] = set()

        # ── 1. Emit DEPENDS_ON relationships from constructor dependencies ────
        for owner_qname, dep_list in type_index.deps_by_owner.items():
            for dep in dep_list:
                if dep.resolved_type_qname:
                    edge_key = (owner_qname, dep.resolved_type_qname, "DEPENDS_ON")
                    if edge_key not in emitted_keys:
                        emitted_keys.add(edge_key)
                        results.append(ResolutionResult(
                            source_id=owner_qname,
                            target_id=dep.resolved_type_qname,
                            relationship="DEPENDS_ON",
                            resolution=dep.resolution,
                            evidence_type=dep.evidence_type,
                            reason=f"Class '{owner_qname}' injects dependency '{dep.dep_name}: {dep.dep_type}'",
                            metadata={"dep_name": dep.dep_name, "dep_type": dep.dep_type}
                        ))

        # ── 2. Emit IMPLEMENTS relationships ──────────────────────────────────
        for tf in type_index.types_by_qname.values():
            for base_qname in type_index.inheritance_index.get(tf.qualified_name, []):
                edge_key = (tf.qualified_name, base_qname, "IMPLEMENTS")
                if edge_key not in emitted_keys:
                    emitted_keys.add(edge_key)
                    results.append(ResolutionResult(
                        source_id=tf.qualified_name,
                        target_id=base_qname,
                        relationship="IMPLEMENTS",
                        resolution="exact",
                        evidence_type="base_class_declaration",
                        reason=f"Type '{tf.qualified_name}' implements/inherits '{base_qname}'",
                        source_file=tf.file_path
                    ))

        # ── 3. Resolve Function & Method Calls ────────────────────────────────
        for pfile in parsed_files:
            content = contents.get(pfile.path, "")
            
            # Top-level functions
            for func in pfile.functions:
                func_results = self._resolve_function_calls(
                    pfile=pfile,
                    func=func,
                    owner_class=None,
                    type_index=type_index,
                    content=content
                )
                for res in func_results:
                    key = (res.source_id, res.target_id, res.relationship)
                    if key not in emitted_keys:
                        emitted_keys.add(key)
                        results.append(res)

            # Class methods
            for cls in pfile.classes:
                for method in cls.methods:
                    method_results = self._resolve_function_calls(
                        pfile=pfile,
                        func=method,
                        owner_class=cls,
                        type_index=type_index,
                        content=content
                    )
                    for res in method_results:
                        key = (res.source_id, res.target_id, res.relationship)
                        if key not in emitted_keys:
                            emitted_keys.add(key)
                            results.append(res)

        logger.info(
            "dependency_aware_resolution_complete",
            total_resolved=len(results),
            depends_on_count=sum(1 for r in results if r.relationship == "DEPENDS_ON"),
            implements_count=sum(1 for r in results if r.relationship == "IMPLEMENTS"),
            calls_count=sum(1 for r in results if r.relationship == "CALLS" and r.resolution == "exact")
        )
        return results

    def _resolve_function_calls(
        self,
        pfile: ParsedFile,
        func: ParsedFunction,
        owner_class: Optional[ParsedClass],
        type_index: RepositoryTypeIndex,
        content: str
    ) -> List[ResolutionResult]:
        results: List[ResolutionResult] = []
        local_receiver_types = self._extract_local_receiver_types(pfile, func, content)

        # Field dependencies available if inside a class method
        owner_deps: Dict[str, DependencyFact] = {}
        if owner_class:
            for df in type_index.deps_by_owner.get(owner_class.qualified_name, []):
                owner_deps[df.dep_name] = df
                owner_deps[f"_{df.dep_name}"] = df
                owner_deps[f"this.{df.dep_name}"] = df
                owner_deps[f"self.{df.dep_name}"] = df

        # Collect candidate call (receiver_str, method_name, raw_call_text)
        call_candidates: List[Tuple[str, str, str]] = []

        # 1. From IR calls
        for call in func.calls:
            raw_name = call.raw_name
            if "." in raw_name or "::" in raw_name:
                sep = "::" if "::" in raw_name else "."
                parts = raw_name.split(sep)
                if len(parts) == 2:
                    call_candidates.append((parts[0].strip(), parts[1].strip(), raw_name))

        # 2. From function body text scan
        if content:
            lines = content.splitlines()
            start = max(0, func.start_line - 1)
            end = min(len(lines), func.end_line)
            func_text = "\n".join(lines[start:end])
            for m in self._MEMBER_CALL_RE.finditer(func_text):
                rec, method = m.group(1).strip(), m.group(2).strip()
                call_candidates.append((rec, method, f"{rec}.{method}"))

        # Deduplicate candidates
        seen_calls: Set[Tuple[str, str]] = set()

        for receiver_str, method_name, raw_name in call_candidates:
            if (receiver_str, method_name) in seen_calls:
                continue
            seen_calls.add((receiver_str, method_name))

            # ── A. Static / Class method call: TypeName.method() or TypeName::method() ──
            target_tf = type_index.find_type_by_name(receiver_str, context_file=pfile.path)
            if target_tf:
                matched = type_index.find_method_in_hierarchy(target_tf, method_name)
                if matched:
                    target_func, defining_tf = matched
                    results.append(ResolutionResult(
                        source_id=func.qualified_name,
                        target_id=target_func.qualified_name,
                        relationship="CALLS",
                        resolution="exact",
                        evidence_type="static_method_call",
                        reason=f"Static call '{raw_name}' in '{func.name}' resolved to '{target_func.qualified_name}'",
                        source_language=pfile.language,
                        target_language=defining_tf.language,
                        source_file=pfile.path,
                        target_file=defining_tf.file_path
                    ))
                    continue

            # ── B. Injected Field Dependency Call: self.repo.charge() ──
            clean_rec = receiver_str.lstrip("self.").lstrip("this.").lstrip("_")
            matched_dep = owner_deps.get(receiver_str) or owner_deps.get(clean_rec)
            if matched_dep and matched_dep.resolved_type_qname:
                dep_tf = type_index.types_by_qname.get(matched_dep.resolved_type_qname)
                if dep_tf:
                    effective_tf = dep_tf
                    ev_type = "injected_dependency_call"
                    if dep_tf.is_interface or "I" in dep_tf.simple_name:
                        concrete_tf, di_ev = type_index.get_concrete_type_for_interface(dep_tf.simple_name)
                        if concrete_tf:
                            effective_tf = concrete_tf
                            ev_type = di_ev

                    matched = type_index.find_method_in_hierarchy(effective_tf, method_name)
                    if matched:
                        target_func, defining_tf = matched
                        results.append(ResolutionResult(
                            source_id=func.qualified_name,
                            target_id=target_func.qualified_name,
                            relationship="CALLS",
                            resolution="exact",
                            evidence_type=ev_type,
                            reason=f"Injected dependency call '{raw_name}' in '{func.name}' resolved to '{target_func.qualified_name}'",
                            source_language=pfile.language,
                            target_language=defining_tf.language,
                            source_file=pfile.path,
                            target_file=defining_tf.file_path
                        ))
                        continue

            # ── C. Local Receiver Type Call: service.charge() ──
            clean_var = receiver_str.lstrip("self.").lstrip("this.")
            var_type_name = local_receiver_types.get(clean_var) or local_receiver_types.get(receiver_str)
            if var_type_name:
                target_tf = type_index.find_type_by_name(var_type_name, context_file=pfile.path)
                if target_tf:
                    effective_tf = target_tf
                    ev_type = "receiver_type_proven"
                    if target_tf.is_interface or "I" in target_tf.simple_name:
                        concrete_tf, di_ev = type_index.get_concrete_type_for_interface(target_tf.simple_name)
                        if concrete_tf:
                            effective_tf = concrete_tf
                            ev_type = di_ev

                    matched = type_index.find_method_in_hierarchy(effective_tf, method_name)
                    if matched:
                        target_func, defining_tf = matched
                        results.append(ResolutionResult(
                            source_id=func.qualified_name,
                            target_id=target_func.qualified_name,
                            relationship="CALLS",
                            resolution="exact",
                            evidence_type=ev_type,
                            reason=f"Local receiver call '{raw_name}' with proven type '{effective_tf.simple_name}' resolved to '{target_func.qualified_name}'",
                            source_language=pfile.language,
                            target_language=defining_tf.language,
                            source_file=pfile.path,
                            target_file=defining_tf.file_path
                        ))
                        continue

        return results

    def _extract_local_receiver_types(
        self,
        pfile: ParsedFile,
        func: ParsedFunction,
        content: str
    ) -> Dict[str, str]:
        """
        Extracts bounded local variable -> type facts from function text.
        """
        type_map: Dict[str, str] = {}
        if not content:
            return type_map

        lines = content.splitlines()
        start = max(0, func.start_line - 1)
        end = min(len(lines), func.end_line)
        func_text = "\n".join(lines[start:end])

        lang = pfile.language

        # 1. JS / TS: const service = new PaymentService() or const service: PaymentService
        if lang in ("typescript", "javascript"):
            for m in self._NEW_INST_RE.finditer(func_text):
                var_name, type_annot, class_name = m.group(1), m.group(2), m.group(3)
                type_map[var_name] = class_name or type_annot

        # 2. Python: service = PaymentService()
        elif lang == "python":
            for m in self._PYTHON_INST_RE.finditer(func_text):
                var_name, type_annot, class_name = m.group(1), m.group(2), m.group(3)
                type_map[var_name] = class_name or type_annot

        # 3. Java / C#: PaymentService service = new PaymentService() or var service = new PaymentService()
        elif lang in ("java", "csharp"):
            for m in self._JAVA_CSHARP_TYPED_VAR_RE.finditer(func_text):
                type_name, var_name, concrete_name = m.group(1), m.group(2), m.group(3)
                type_map[var_name] = concrete_name or type_name
            for m in self._NEW_INST_RE.finditer(func_text):
                var_name, type_annot, class_name = m.group(1), m.group(2), m.group(3)
                type_map[var_name] = class_name or type_annot

        # 4. Go: service := NewPaymentService() or service := &PaymentService{}
        elif lang == "go":
            for m in self._GO_INST_RE.finditer(func_text):
                var_name, new_type, struct_type = m.group(1), m.group(2), m.group(3)
                type_map[var_name] = new_type or struct_type

        # 5. Rust: let service = PaymentService::new()
        elif lang == "rust":
            for m in self._RUST_INST_RE.finditer(func_text):
                var_name, type_annot, class_name = m.group(1), m.group(2), m.group(3)
                type_map[var_name] = class_name or type_annot

        return type_map
