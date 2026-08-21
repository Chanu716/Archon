"""
Repository-Wide Type & Dependency Index (Slice ML-10)

Maintains snapshot-scoped indexes for:
  - Type declarations (Class, Interface, Struct, Trait)
  - Inheritance / Implements relationships
  - Constructor & factory dependency injection facts
  - Framework DI container bindings (ASP.NET Core, Spring Boot)
  - Method membership across type hierarchies
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
import posixpath
import structlog

from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction
from archon.pipeline.resolution.imports import ModuleSymbolIndex, _normalize_repo_path
from archon.pipeline.resolution.dependency_extractor import DependencyExtractor, RawDependency, RawDIBinding

logger = structlog.get_logger(__name__)

MAX_TYPE_HIERARCHY_DEPTH = 5
MAX_DI_CHAIN_DEPTH = 3


@dataclass
class TypeFact:
    """Represents a discovered class, interface, struct, or trait."""
    qualified_name: str
    simple_name: str
    language: str
    file_path: str
    base_classes: List[str] = field(default_factory=list)
    methods: Dict[str, ParsedFunction] = field(default_factory=dict)
    is_interface: bool = False
    is_abstract: bool = False
    docstring: Optional[str] = None


@dataclass
class DependencyFact:
    """Represents a constructor or factory injected dependency."""
    owner_class_qname: str
    dep_name: str
    dep_type: str
    resolved_type_qname: Optional[str] = None
    resolution: str = "unresolved"  # "exact" | "inferred" | "unresolved"
    evidence_type: str = "constructor_type_annotation"
    file_path: str = ""


@dataclass
class DIBindingFact:
    """Represents an explicit DI container binding (e.g. AddScoped<IFoo, Foo>)."""
    interface_type: str
    concrete_type: str
    framework: str
    evidence_type: str = "dependency_injection_binding"
    source_file: str = ""
    resolved_interface_qname: Optional[str] = None
    resolved_concrete_qname: Optional[str] = None


class RepositoryTypeIndex:
    """
    Snapshot-scoped type, inheritance, dependency, and DI binding index.
    """

    def __init__(
        self,
        parsed_files: List[ParsedFile],
        file_contents: Optional[Dict[str, str]] = None,
        module_symbol_index: Optional[ModuleSymbolIndex] = None
    ):
        self.parsed_files = parsed_files
        self.file_contents = file_contents or {}
        self.module_symbol_index = module_symbol_index or ModuleSymbolIndex(parsed_files, self.file_contents)

        # ── Lookup tables ──
        self.types_by_qname: Dict[str, TypeFact] = {}
        self.types_by_simple_name: Dict[str, List[TypeFact]] = {}
        self.methods_by_type: Dict[str, Dict[str, ParsedFunction]] = {}
        self.deps_by_owner: Dict[str, List[DependencyFact]] = {}
        self.di_bindings_by_iface: Dict[str, List[DIBindingFact]] = {}
        self.inheritance_index: Dict[str, List[str]] = {}  # class_qname -> list of base_class_qnames
        self.implementations_by_iface: Dict[str, List[TypeFact]] = {}  # iface_name/qname -> list of implementing TypeFacts

        self._build_index()

    def _build_index(self):
        # 1. Collect all types and their methods
        for pfile in self.parsed_files:
            for cls in pfile.classes:
                is_iface = (
                    cls.name.startswith("I") and len(cls.name) > 1 and cls.name[1].isupper()
                    if pfile.language in ("csharp", "typescript")
                    else "interface" in (cls.docstring or "").lower()
                )
                methods_dict: Dict[str, ParsedFunction] = {}
                for m in cls.methods:
                    methods_dict[m.name] = m
                    methods_dict[m.qualified_name] = m

                tf = TypeFact(
                    qualified_name=cls.qualified_name,
                    simple_name=cls.name,
                    language=pfile.language,
                    file_path=pfile.path,
                    base_classes=list(cls.base_classes),
                    methods=methods_dict,
                    is_interface=is_iface,
                    is_abstract="abstract" in (cls.docstring or "").lower(),
                    docstring=cls.docstring
                )
                self.types_by_qname[cls.qualified_name] = tf
                self.types_by_simple_name.setdefault(cls.name, []).append(tf)
                self.methods_by_type[cls.qualified_name] = methods_dict

        # 2. Build inheritance & implementation graph
        for tf in self.types_by_qname.values():
            resolved_bases: List[str] = []
            for base_name in tf.base_classes:
                base_tf = self.find_type_by_name(base_name, context_file=tf.file_path)
                if base_tf:
                    resolved_bases.append(base_tf.qualified_name)
                    self.implementations_by_iface.setdefault(base_tf.qualified_name, []).append(tf)
                    self.implementations_by_iface.setdefault(base_tf.simple_name, []).append(tf)
                else:
                    self.implementations_by_iface.setdefault(base_name, []).append(tf)
            self.inheritance_index[tf.qualified_name] = resolved_bases

        # 3. Extract raw dependencies and DI bindings
        extractor = DependencyExtractor()
        raw_deps, raw_di = extractor.extract_dependencies(self.parsed_files, self.file_contents)

        # 4. Resolve DI bindings
        for di in raw_di:
            iface_tf = self.find_type_by_name(di.interface_type, context_file=di.source_file)
            concrete_tf = self.find_type_by_name(di.concrete_type, context_file=di.source_file)

            binding = DIBindingFact(
                interface_type=di.interface_type,
                concrete_type=di.concrete_type,
                framework=di.framework,
                evidence_type=di.evidence_type,
                source_file=di.source_file,
                resolved_interface_qname=iface_tf.qualified_name if iface_tf else None,
                resolved_concrete_qname=concrete_tf.qualified_name if concrete_tf else None
            )
            self.di_bindings_by_iface.setdefault(di.interface_type, []).append(binding)
            if iface_tf:
                self.di_bindings_by_iface.setdefault(iface_tf.qualified_name, []).append(binding)

        # 5. Resolve constructor dependencies
        for rdep in raw_deps:
            target_tf = self.find_type_by_name(rdep.dep_type, context_file=rdep.file_path)
            res = "exact" if target_tf is not None else "unresolved"
            df = DependencyFact(
                owner_class_qname=rdep.owner_class_qname,
                dep_name=rdep.dep_name,
                dep_type=rdep.dep_type,
                resolved_type_qname=target_tf.qualified_name if target_tf else None,
                resolution=res,
                evidence_type=rdep.evidence_type,
                file_path=rdep.file_path
            )
            self.deps_by_owner.setdefault(rdep.owner_class_qname, []).append(df)

    def find_type_by_name(self, name: str, context_file: Optional[str] = None) -> Optional[TypeFact]:
        """
        Deterministically finds a TypeFact by qualified name or simple name.
        Uses context_file imports when available.
        """
        # Exact qualified name match
        if name in self.types_by_qname:
            return self.types_by_qname[name]

        # Context-file import resolution
        if context_file:
            norm_ctx = _normalize_repo_path(context_file)
            pfile = self.module_symbol_index.file_by_path.get(norm_ctx)
            if pfile:
                for imp in pfile.imports:
                    local_name = imp.alias if imp.alias else imp.name
                    if local_name == name:
                        target_pfile, _ = self.module_symbol_index.file_by_path.get(norm_ctx), None
                        # Check classes in target
                        for c in self.types_by_qname.values():
                            if c.simple_name == imp.name and (imp.module and imp.module in c.qualified_name):
                                return c

        # Simple name lookup
        candidates = self.types_by_simple_name.get(name, [])
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1 and context_file:
            # Prefer type in same file or same directory
            norm_ctx = _normalize_repo_path(context_file)
            ctx_dir = posixpath.dirname(norm_ctx)
            same_file = [c for c in candidates if _normalize_repo_path(c.file_path) == norm_ctx]
            if len(same_file) == 1:
                return same_file[0]
            same_dir = [c for c in candidates if posixpath.dirname(_normalize_repo_path(c.file_path)) == ctx_dir]
            if len(same_dir) == 1:
                return same_dir[0]

        # If still ambiguous or not found -> None (conservative, no guessing)
        return None

    def find_method_in_hierarchy(
        self,
        type_fact: TypeFact,
        method_name: str,
        max_depth: int = MAX_TYPE_HIERARCHY_DEPTH,
        visited: Optional[Set[str]] = None
    ) -> Optional[Tuple[ParsedFunction, TypeFact]]:
        """
        Recursively searches for method_name in type_fact and its base classes / interfaces.
        Cycle-safe and depth-bounded.
        Returns: (ParsedFunction, TypeFact where method is defined)
        """
        if visited is None:
            visited = set()

        if type_fact.qualified_name in visited or max_depth <= 0:
            return None
        visited.add(type_fact.qualified_name)

        # 1. Direct method on type
        if method_name in type_fact.methods:
            return type_fact.methods[method_name], type_fact

        # 2. Search base classes / interfaces
        base_qnames = self.inheritance_index.get(type_fact.qualified_name, [])
        for base_qname in base_qnames:
            base_tf = self.types_by_qname.get(base_qname)
            if base_tf:
                res = self.find_method_in_hierarchy(base_tf, method_name, max_depth - 1, visited)
                if res:
                    return res

        # Also search simple base class names if qualified not found
        for base_name in type_fact.base_classes:
            base_tf = self.find_type_by_name(base_name, context_file=type_fact.file_path)
            if base_tf and base_tf.qualified_name not in visited:
                res = self.find_method_in_hierarchy(base_tf, method_name, max_depth - 1, visited)
                if res:
                    return res

        return None

    def get_concrete_type_for_interface(self, interface_name: str) -> Tuple[Optional[TypeFact], str]:
        """
        Determines the concrete implementation TypeFact for an interface or abstract type.
        Returns (TypeFact, evidence_type).
        """
        # 1. Check explicit DI binding
        bindings = self.di_bindings_by_iface.get(interface_name, [])
        if len(bindings) == 1:
            b = bindings[0]
            if b.resolved_concrete_qname and b.resolved_concrete_qname in self.types_by_qname:
                return self.types_by_qname[b.resolved_concrete_qname], "dependency_injection_binding"
            concrete_tf = self.find_type_by_name(b.concrete_type)
            if concrete_tf:
                return concrete_tf, "dependency_injection_binding"

        # 2. Check unique implementation in repository
        impls = self.implementations_by_iface.get(interface_name, [])
        if len(impls) == 1:
            return impls[0], "unique_interface_implementation"

        return None, "unresolved"
