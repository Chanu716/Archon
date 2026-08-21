"""
Deterministic Architecture Classifier (Slice ML-11)

Classifies repository classes, structs, and functions into architectural roles:
  - controller
  - endpoint_handler
  - service
  - repository
  - gateway
  - client
  - component
  - domain
  - infrastructure
  - utility
  - unknown

Zero speculation rule:
  - Naming alone NEVER produces an exact classification.
  - Framework annotations/attributes produce EXACT classifications.
  - Structural graph topology (HANDLED_BY, DEPENDS_ON, CALLS, REQUESTS) produces INFERRED classifications.
  - Insufficient evidence safely defaults to UNKNOWN.
"""

import re
from typing import List, Dict, Optional, Set
import structlog

from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.architecture.models import (
    ArchitectureRole,
    ArchitectureLayer,
    ArchitectureNodeFact,
    ROLE_TO_LAYER,
)

logger = structlog.get_logger(__name__)


class ArchitectureClassifier:
    """
    Classifies classes and functions into deterministic architectural roles and layers.
    """

    # Framework Annotation Regex Patterns
    _SPRING_CONTROLLER_RE = re.compile(r'@(?:Rest)?Controller\b')
    _SPRING_SERVICE_RE = re.compile(r'@Service\b')
    _SPRING_REPOSITORY_RE = re.compile(r'@Repository\b')
    _ASPNET_CONTROLLER_RE = re.compile(r'\[(?:ApiController|Route|HttpGet|HttpPost|HttpPut|HttpDelete)\b')

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

    def classify_repository(
        self,
        parsed_files: List[ParsedFile],
        resolved_facts: List[ResolutionResult],
        file_contents: Optional[Dict[str, str]] = None
    ) -> Dict[str, ArchitectureNodeFact]:
        contents = file_contents or {}
        facts: Dict[str, ArchitectureNodeFact] = {}

        # 1. Index resolved facts
        handled_by_handlers: Set[str] = set()
        requests_callers: Set[str] = set()
        depends_on_map: Dict[str, Set[str]] = {}  # source -> set of targets
        dependent_of_map: Dict[str, Set[str]] = {} # target -> set of sources

        for rel in resolved_facts:
            if rel.relationship == "HANDLED_BY":
                handled_by_handlers.add(rel.target_id)
            elif rel.relationship == "REQUESTS":
                requests_callers.add(rel.source_id)
            elif rel.relationship == "DEPENDS_ON":
                depends_on_map.setdefault(rel.source_id, set()).add(rel.target_id)
                dependent_of_map.setdefault(rel.target_id, set()).add(rel.source_id)

        # 2. First pass: Classify Classes & Structs
        for pfile in parsed_files:
            file_text = contents.get(pfile.path, "")
            for cls in pfile.classes:
                fact = self._classify_class(
                    cls=cls,
                    pfile=pfile,
                    file_text=file_text,
                    handled_by_handlers=handled_by_handlers,
                    requests_callers=requests_callers,
                    depends_on_map=depends_on_map,
                    dependent_of_map=dependent_of_map
                )
                facts[cls.qualified_name] = fact

            # 3. Second pass: Classify Top-level Functions
            for func in pfile.functions:
                fact = self._classify_function(
                    func=func,
                    pfile=pfile,
                    handled_by_handlers=handled_by_handlers,
                    requests_callers=requests_callers
                )
                facts[func.qualified_name] = fact

        # 4. Third pass: Refine Inferred Services and Repositories using classified neighbors
        self._refine_inferred_roles(facts, depends_on_map, dependent_of_map)

        logger.info(
            "architecture_classification_complete",
            total_classified=len(facts),
            controllers=sum(1 for f in facts.values() if f.architecture_role == ArchitectureRole.CONTROLLER),
            services=sum(1 for f in facts.values() if f.architecture_role == ArchitectureRole.SERVICE),
            repositories=sum(1 for f in facts.values() if f.architecture_role == ArchitectureRole.REPOSITORY),
            unknown=sum(1 for f in facts.values() if f.architecture_role == ArchitectureRole.UNKNOWN),
            snapshot_id=self.snapshot_id
        )
        return facts

    def _classify_class(
        self,
        cls: ParsedClass,
        pfile: ParsedFile,
        file_text: str,
        handled_by_handlers: Set[str],
        requests_callers: Set[str],
        depends_on_map: Dict[str, Set[str]],
        dependent_of_map: Dict[str, Set[str]]
    ) -> ArchitectureNodeFact:
        # Collect class slice text (including 10 lines preceding class declaration for annotations)
        class_header_text = ""
        if file_text:
            lines = file_text.splitlines()
            start = max(0, cls.start_line - 10)
            end = min(len(lines), cls.end_line)
            class_header_text = "\n".join(lines[start:end])

        doc_lower = (cls.docstring or "").lower()

        # Check method decorators
        method_decorators_lower = set()
        for m in cls.methods:
            for dec in m.decorators:
                method_decorators_lower.add(dec.lower().strip("@[]"))

        # Check if any method is target of HANDLED_BY
        has_endpoint_handler = any(
            m.qualified_name in handled_by_handlers
            or any(h.endswith(f".{m.name}") or h.endswith(f":{m.name}") for h in handled_by_handlers)
            for m in cls.methods
        ) or any(h.startswith(f"{cls.qualified_name}.") or h.startswith(f"{cls.name}.") for h in handled_by_handlers)

        # ── 1. Controller Classification ──
        # Exact: Java @RestController / @Controller, C# [ApiController]
        if (
            self._SPRING_CONTROLLER_RE.search(class_header_text)
            or self._ASPNET_CONTROLLER_RE.search(class_header_text)
            or any(d in method_decorators_lower for d in ("restcontroller", "controller", "apicontroller", "postmapping", "getmapping", "httpget", "httppost"))
        ):
            role = ArchitectureRole.CONTROLLER
            return ArchitectureNodeFact(
                qualified_name=cls.qualified_name,
                node_kind="Class",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="exact",
                evidence_type="framework_controller_annotation",
                evidence="Found controller framework annotation (@RestController / @Controller / [ApiController])",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        if has_endpoint_handler:
            role = ArchitectureRole.CONTROLLER
            return ArchitectureNodeFact(
                qualified_name=cls.qualified_name,
                node_kind="Class",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="inferred",
                evidence_type="endpoint_handler_ownership",
                evidence="Class contains methods registered as HTTP endpoint handlers",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        # ── 2. Service Classification ──
        # Exact: Java @Service
        if self._SPRING_SERVICE_RE.search(class_header_text) or "service" in method_decorators_lower:
            role = ArchitectureRole.SERVICE
            return ArchitectureNodeFact(
                qualified_name=cls.qualified_name,
                node_kind="Class",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="exact",
                evidence_type="framework_service_annotation",
                evidence="Found @Service framework annotation",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        # ── 3. Repository Classification ──
        # Exact: Java @Repository
        if self._SPRING_REPOSITORY_RE.search(class_header_text) or "repository" in method_decorators_lower:
            role = ArchitectureRole.REPOSITORY
            return ArchitectureNodeFact(
                qualified_name=cls.qualified_name,
                node_kind="Class",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="exact",
                evidence_type="framework_repository_annotation",
                evidence="Found @Repository framework annotation",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        # ── 4. Gateway / Client Classification ──
        has_http_call = any(
            m.qualified_name in requests_callers
            or any(r.endswith(f".{m.name}") for r in requests_callers)
            for m in cls.methods
        )
        if has_http_call:
            role = ArchitectureRole.CLIENT
            return ArchitectureNodeFact(
                qualified_name=cls.qualified_name,
                node_kind="Class",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="inferred",
                evidence_type="http_client_caller",
                evidence="Class methods issue HTTP / API requests",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        # ── 5. Component Classification (UI) ──
        if pfile.path.endswith(".tsx") or pfile.path.endswith(".jsx") or "component" in doc_lower:
            role = ArchitectureRole.COMPONENT
            return ArchitectureNodeFact(
                qualified_name=cls.qualified_name,
                node_kind="Class",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="inferred",
                evidence_type="ui_component_file",
                evidence="Defined in UI component source file (.tsx / .jsx)",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        # Default fallback: Unknown (Never guess from name alone)
        return ArchitectureNodeFact(
            qualified_name=cls.qualified_name,
            node_kind="Class",
            architecture_role=ArchitectureRole.UNKNOWN,
            layer=ArchitectureLayer.UNKNOWN,
            resolution="unresolved",
            evidence_type="insufficient_architectural_evidence",
            evidence="No deterministic framework or structural evidence found",
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            file_path=pfile.path,
            language=pfile.language
        )

    def _classify_function(
        self,
        func: ParsedFunction,
        pfile: ParsedFile,
        handled_by_handlers: Set[str],
        requests_callers: Set[str]
    ) -> ArchitectureNodeFact:
        is_handler = (
            func.qualified_name in handled_by_handlers
            or any(h.endswith(f".{func.name}") or h.endswith(f":{func.name}") for h in handled_by_handlers)
        )
        if is_handler:
            role = ArchitectureRole.ENDPOINT_HANDLER
            return ArchitectureNodeFact(
                qualified_name=func.qualified_name,
                node_kind="Function",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="exact",
                evidence_type="endpoint_handler_binding",
                evidence="Function is directly bound as a backend endpoint handler",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        is_client = (
            func.qualified_name in requests_callers
            or any(r.endswith(f".{func.name}") for r in requests_callers)
        )
        if is_client:
            role = ArchitectureRole.CLIENT
            return ArchitectureNodeFact(
                qualified_name=func.qualified_name,
                node_kind="Function",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="inferred",
                evidence_type="http_client_caller",
                evidence="Function issues outbound HTTP client requests",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        if pfile.path.endswith(".tsx") or pfile.path.endswith(".jsx"):
            role = ArchitectureRole.COMPONENT
            return ArchitectureNodeFact(
                qualified_name=func.qualified_name,
                node_kind="Function",
                architecture_role=role,
                layer=ROLE_TO_LAYER[role],
                resolution="inferred",
                evidence_type="ui_component_file",
                evidence="Functional UI component in .tsx / .jsx file",
                repository_id=self.repository_id,
                snapshot_id=self.snapshot_id,
                file_path=pfile.path,
                language=pfile.language
            )

        return ArchitectureNodeFact(
            qualified_name=func.qualified_name,
            node_kind="Function",
            architecture_role=ArchitectureRole.UNKNOWN,
            layer=ArchitectureLayer.UNKNOWN,
            resolution="unresolved",
            evidence_type="insufficient_architectural_evidence",
            evidence="No deterministic framework or structural evidence found",
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            file_path=pfile.path,
            language=pfile.language
        )

    def _refine_inferred_roles(
        self,
        facts: Dict[str, ArchitectureNodeFact],
        depends_on_map: Dict[str, Set[str]],
        dependent_of_map: Dict[str, Set[str]]
    ):
        """
        Infers service or repository roles from dependency topology when annotations are absent.
        """
        def _get_dependents(qname: str) -> Set[str]:
            res = set(dependent_of_map.get(qname, set()))
            for k, v in dependent_of_map.items():
                if k.endswith(f".{qname}") or qname.endswith(f".{k}") or k == qname:
                    res.update(v)
            return res

        def _get_dependencies(qname: str) -> Set[str]:
            res = set(depends_on_map.get(qname, set()))
            for k, v in depends_on_map.items():
                if k.endswith(f".{qname}") or qname.endswith(f".{k}") or k == qname:
                    res.update(v)
            return res

        for qname, fact in list(facts.items()):
            if fact.architecture_role == ArchitectureRole.UNKNOWN:
                outgoing = _get_dependencies(qname)
                incoming = _get_dependents(qname)

                # Check if depended on by a Controller
                called_by_controller = any(
                    any(
                        f.architecture_role == ArchitectureRole.CONTROLLER
                        for f_qname, f in facts.items()
                        if f_qname == src or f_qname.endswith(f".{src}") or src.endswith(f".{f_qname}")
                    )
                    for src in incoming
                )

                if called_by_controller and len(outgoing) > 0:
                    # Inferred Service
                    role = ArchitectureRole.SERVICE
                    facts[qname] = ArchitectureNodeFact(
                        qualified_name=qname,
                        node_kind=fact.node_kind,
                        architecture_role=role,
                        layer=ROLE_TO_LAYER[role],
                        resolution="inferred",
                        evidence_type="dependency_layer_pattern",
                        evidence="Class is injected into Controller and has downstream dependencies",
                        repository_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        file_path=fact.file_path,
                        language=fact.language
                    )
                elif (called_by_controller and len(outgoing) == 0) or ("repository" in qname.lower() and len(incoming) > 0):
                    # Inferred Repository
                    role = ArchitectureRole.REPOSITORY
                    facts[qname] = ArchitectureNodeFact(
                        qualified_name=qname,
                        node_kind=fact.node_kind,
                        architecture_role=role,
                        layer=ROLE_TO_LAYER[role],
                        resolution="inferred",
                        evidence_type="persistence_boundary_pattern",
                        evidence="Class is injected as a leaf dependency from higher architectural layer",
                        repository_id=self.repository_id,
                        snapshot_id=self.snapshot_id,
                        file_path=fact.file_path,
                        language=fact.language
                    )
