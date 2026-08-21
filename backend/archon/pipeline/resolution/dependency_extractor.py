"""
Dependency & DI Binding Extractor (Slice ML-10)

Extracts constructor dependency facts, struct/field wirings,
and explicit DI framework bindings across Python, TypeScript, Java, C#, Go, and Rust.
Strictly static text and AST scanning without runtime evaluation.
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set, Any

from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction, ParsedParameter

@dataclass
class RawDependency:
    owner_class_qname: str
    dep_name: str
    dep_type: str
    evidence_type: str
    file_path: str


@dataclass
class RawDIBinding:
    interface_type: str
    concrete_type: str
    framework: str
    evidence_type: str
    source_file: str


class DependencyExtractor:
    """
    Language-aware extractor for constructor dependencies and DI bindings.
    """

    # ── ASP.NET Core DI patterns ──
    _ASPNET_DI_RE = re.compile(
        r'(?:services|builder\.Services)\.Add(?:Scoped|Singleton|Transient|HostedService)<'
        r'([a-zA-Z0-9_.]+),\s*([a-zA-Z0-9_.]+)>',
        re.IGNORECASE
    )

    # ── Spring Boot @Bean pattern ──
    _SPRING_BEAN_RE = re.compile(
        r'@Bean\b[^{]*?(?:public\s+)?([a-zA-Z0-9_]+)\s+([a-zA-Z0-9_]+)\s*\([^)]*\)\s*\{[^}]*?return\s+new\s+([a-zA-Z0-9_]+)\s*\(',
        re.DOTALL
    )

    # ── Constructor regex fallbacks for typed languages ──
    # Java/C#: public OrderService(OrderRepository repository)
    _JAVA_CSHARP_CTOR_PARAM_RE = re.compile(
        r'(?:public|protected|private)?\s*(?:[a-zA-Z0-9_]+)\s*\(\s*([^)]+)\s*\)\s*\{'
    )
    # Python: def __init__(self, repo: OrderRepository, gateway: PaymentGateway)
    _PYTHON_INIT_PARAM_RE = re.compile(
        r'def\s+__init__\s*\(\s*self\s*,\s*([^)]+)\s*\):'
    )
    # Go: func NewOrderService(repo OrderRepository)
    _GO_NEW_RE = re.compile(
        r'func\s+New([A-Z][a-zA-Z0-9_]*)\s*\(\s*([^)]*)\s*\)\s*\*?([A-Z][a-zA-Z0-9_]*)'
    )
    # Rust: fn new(repository: Arc<OrderRepository>)
    _RUST_NEW_RE = re.compile(
        r'fn\s+new\s*\(\s*([^)]*)\s*\)'
    )

    _RUST_CONTAINER_RE = re.compile(r'^(?:Arc|Rc|Box|Option|RefCell|Mutex|RwLock)<\s*([a-zA-Z0-9_:]+)\s*>$')

    def extract_dependencies(
        self,
        parsed_files: List[ParsedFile],
        file_contents: Dict[str, str]
    ) -> Tuple[List[RawDependency], List[RawDIBinding]]:
        deps: List[RawDependency] = []
        di_bindings: List[RawDIBinding] = []

        for pfile in parsed_files:
            content = file_contents.get(pfile.path, "")
            
            # Extract DI bindings from file content
            file_bindings = self._extract_di_bindings(pfile, content)
            di_bindings.extend(file_bindings)

            # Extract constructor dependencies per class
            for cls in pfile.classes:
                class_deps = self._extract_class_dependencies(pfile, cls, content)
                deps.extend(class_deps)

            # Language-specific top-level factory extractions (e.g. Go factory functions)
            if pfile.language == "go":
                go_deps = self._extract_go_factory_dependencies(pfile, content)
                deps.extend(go_deps)

        return deps, di_bindings

    def _extract_di_bindings(self, pfile: ParsedFile, content: str) -> List[RawDIBinding]:
        bindings: List[RawDIBinding] = []
        if not content:
            return bindings

        # 1. C# ASP.NET Core DI
        if pfile.language == "csharp":
            for m in self._ASPNET_DI_RE.finditer(content):
                iface, concrete = m.group(1).strip(), m.group(2).strip()
                bindings.append(RawDIBinding(
                    interface_type=iface,
                    concrete_type=concrete,
                    framework="aspnetcore",
                    evidence_type="dependency_injection_binding",
                    source_file=pfile.path
                ))

        # 2. Java Spring Boot @Bean
        elif pfile.language == "java":
            for m in self._SPRING_BEAN_RE.finditer(content):
                iface_type, bean_name, concrete_type = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
                if iface_type != concrete_type:
                    bindings.append(RawDIBinding(
                        interface_type=iface_type,
                        concrete_type=concrete_type,
                        framework="spring_boot",
                        evidence_type="dependency_injection_binding",
                        source_file=pfile.path
                    ))

        return bindings

    def _extract_class_dependencies(
        self,
        pfile: ParsedFile,
        cls: ParsedClass,
        content: str
    ) -> List[RawDependency]:
        deps: List[RawDependency] = []
        lang = pfile.language

        # ── 1. Python ──────────────────────────────────────────────────────────
        if lang == "python":
            init_func = next((m for m in cls.methods if m.name == "__init__"), None)
            if init_func:
                for param in init_func.parameters:
                    if isinstance(param, ParsedParameter):
                        if param.name not in ("self", "cls") and param.type_annotation:
                            deps.append(RawDependency(
                                owner_class_qname=cls.qualified_name,
                                dep_name=param.name,
                                dep_type=param.type_annotation.strip(),
                                evidence_type="constructor_type_annotation",
                                file_path=pfile.path
                            ))
                    elif isinstance(param, str):
                        pass

        # ── 2. TypeScript / JavaScript ────────────────────────────────────────
        elif lang in ("typescript", "javascript"):
            ctor = next((m for m in cls.methods if m.name == "constructor"), None)
            if ctor:
                for param in ctor.parameters:
                    if isinstance(param, ParsedParameter) and param.type_annotation:
                        deps.append(RawDependency(
                            owner_class_qname=cls.qualified_name,
                            dep_name=param.name,
                            dep_type=param.type_annotation.strip(),
                            evidence_type="constructor_type_annotation",
                            file_path=pfile.path
                        ))

        # ── 3. Java / C# ───────────────────────────────────────────────────────
        elif lang in ("java", "csharp"):
            # Check constructors from methods or content regex
            # First check if parameters are ParsedParameter
            ctors = [m for m in cls.methods if m.name == cls.name]
            found = False
            for ctor in ctors:
                for param in ctor.parameters:
                    if isinstance(param, ParsedParameter) and param.type_annotation:
                        deps.append(RawDependency(
                            owner_class_qname=cls.qualified_name,
                            dep_name=param.name,
                            dep_type=param.type_annotation.strip(),
                            evidence_type="constructor_type_annotation",
                            file_path=pfile.path
                        ))
                        found = True

            # If not found or parameters were strings, parse from class content
            if not found and content:
                # Find constructor matching this class name
                ctor_pattern = re.compile(
                    r'(?:public|protected|private)?\s*' + re.escape(cls.name) + r'\s*\(\s*([^)]+)\s*\)\s*\{'
                )
                for m in ctor_pattern.finditer(content):
                    params_str = m.group(1).strip()
                    for param_part in params_str.split(","):
                        parts = param_part.strip().split()
                        if len(parts) >= 2:
                            ptype, pname = parts[-2].strip(), parts[-1].strip()
                            if ptype not in ("int", "long", "float", "double", "bool", "boolean", "char", "byte", "string", "String", "void", "var"):
                                deps.append(RawDependency(
                                    owner_class_qname=cls.qualified_name,
                                    dep_name=pname,
                                    dep_type=ptype,
                                    evidence_type="constructor_type_annotation",
                                    file_path=pfile.path
                                ))

        # ── 4. Rust ───────────────────────────────────────────────────────────
        elif lang == "rust":
            new_fn = next((m for m in cls.methods if m.name == "new"), None)
            if new_fn:
                for param in new_fn.parameters:
                    if isinstance(param, ParsedParameter):
                        if param.name not in ("self", "&self", "&mut self") and param.type_annotation:
                            unwrapped = self._unwrap_rust_type(param.type_annotation.strip())
                            deps.append(RawDependency(
                                owner_class_qname=cls.qualified_name,
                                dep_name=param.name,
                                dep_type=unwrapped,
                                evidence_type="constructor_type_annotation",
                                file_path=pfile.path
                            ))

        return deps

    def _unwrap_rust_type(self, raw_type: str) -> str:
        m = self._RUST_CONTAINER_RE.match(raw_type)
        if m:
            return m.group(1).strip()
        return raw_type

    def _extract_go_factory_dependencies(
        self,
        pfile: ParsedFile,
        content: str
    ) -> List[RawDependency]:
        """
        Extracts Go factory/constructor patterns:
        func NewOrderService(repo OrderRepository) *OrderService { ... }
        """
        deps: List[RawDependency] = []
        if not content:
            return deps

        for m in self._GO_NEW_RE.finditer(content):
            fn_suffix, params_str, ret_type = m.group(1), m.group(2).strip(), m.group(3).strip()
            target_struct = ret_type if ret_type else fn_suffix
            owner_qname = f"{pfile.module_name or pfile.path}.{target_struct}"

            for param_part in params_str.split(","):
                parts = param_part.strip().split()
                if len(parts) >= 2:
                    pname, ptype = parts[0].strip(), parts[1].strip().lstrip("*")
                    if ptype not in ("string", "int", "int64", "bool", "float64", "error"):
                        deps.append(RawDependency(
                            owner_class_qname=owner_qname,
                            dep_name=pname,
                            dep_type=ptype,
                            evidence_type="go_factory_wiring",
                            file_path=pfile.path
                        ))
        return deps
