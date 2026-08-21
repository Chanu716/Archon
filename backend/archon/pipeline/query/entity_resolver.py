"""
Deterministic Entity Resolver (Slice ML-13)

Translates raw query entity references into canonical architecture entities.

Supports:
  - Exact qualified names (e.g. 'MyApp.Services.OrderService')
  - Exact endpoint identities ('POST /api/v1/orders' or 'endpoint:POST:/api/v1/orders')
  - Unambiguous short symbol names ('OrderService')
  - Module/file path identities ('services/billing' or 'src/services/billing.ts')

Guarantees:
  - Exact match priority.
  - Explicit ambiguity surfacing (no heuristics, no speculative guessing).
  - Strict repository and snapshot scoping.
  - Zero fuzzy matching or edit-distance approximations.
"""

from typing import List, Dict, Optional, Set
import re
import structlog

from archon.pipeline.evolution.models import SnapshotEntityFact
from archon.pipeline.query.models import (
    ResolvedEntity,
    EntityResolutionResult,
    EntityResolutionStatus,
    ResolutionConfidence,
)

logger = structlog.get_logger(__name__)


class EntityResolver:
    """
    Deterministically resolves entity query references against snapshot entity facts.
    """

    def __init__(self, repository_id: str, snapshot_id: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

    def resolve(
        self,
        query_string: str,
        entities: Dict[str, SnapshotEntityFact],
    ) -> EntityResolutionResult:
        if not query_string or not query_string.strip():
            return EntityResolutionResult(
                query_string=query_string,
                status=EntityResolutionStatus.NOT_FOUND,
                message="Empty query string provided.",
            )

        q_clean = query_string.strip()

        # 1. Check Exact Canonical Qualified Name Match
        if q_clean in entities:
            ent_fact = entities[q_clean]
            resolved = self._to_resolved_entity(ent_fact)
            return EntityResolutionResult(
                query_string=q_clean,
                status=EntityResolutionStatus.RESOLVED,
                entity=resolved,
                candidates=[resolved],
                message=f"Exact match found for '{q_clean}'.",
            )

        # 2. Check HTTP Endpoint Formats
        # e.g., 'POST /api/v1/orders' -> 'endpoint:POST:/api/v1/orders'
        endpoint_candidate = None
        if " " in q_clean:
            parts = q_clean.split(None, 1)
            if len(parts) == 2 and parts[0].upper() in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
                method = parts[0].upper()
                path = parts[1].strip()
                if not path.startswith("/"):
                    path = "/" + path
                norm_ep_id = f"endpoint:{method}:{path}"
                if norm_ep_id in entities:
                    resolved = self._to_resolved_entity(entities[norm_ep_id])
                    return EntityResolutionResult(
                        query_string=q_clean,
                        status=EntityResolutionStatus.RESOLVED,
                        entity=resolved,
                        candidates=[resolved],
                        message=f"Exact HTTP endpoint match found for '{norm_ep_id}'.",
                    )

        # 3. Check Exact Simple Symbol Name (e.g. 'OrderService' or 'checkout')
        matching_symbols: List[ResolvedEntity] = []
        for qname, fact in entities.items():
            # Check last segment of qualified name
            simple_name = qname.split(".")[-1].split("::")[-1].split("/")[-1]
            if simple_name == q_clean:
                matching_symbols.append(self._to_resolved_entity(fact))

        if len(matching_symbols) == 1:
            return EntityResolutionResult(
                query_string=q_clean,
                status=EntityResolutionStatus.RESOLVED,
                entity=matching_symbols[0],
                candidates=matching_symbols,
                message=f"Unambiguous short name match for '{q_clean}' -> '{matching_symbols[0].qualified_name}'.",
            )
        elif len(matching_symbols) > 1:
            return EntityResolutionResult(
                query_string=q_clean,
                status=EntityResolutionStatus.AMBIGUOUS,
                entity=None,
                candidates=sorted(matching_symbols, key=lambda e: e.qualified_name),
                message=(
                    f"Ambiguous query '{q_clean}' matched {len(matching_symbols)} candidates: "
                    f"{', '.join(e.qualified_name for e in matching_symbols)}. Please specify the full qualified name."
                ),
            )

        # 4. Check Module / File Path Match
        matching_paths: List[ResolvedEntity] = []
        norm_q_path = q_clean.replace("\\", "/").strip("/")
        for qname, fact in entities.items():
            if fact.file_path:
                norm_file_path = fact.file_path.replace("\\", "/").strip("/")
                if norm_file_path.endswith(norm_q_path) or norm_q_path == norm_file_path:
                    matching_paths.append(self._to_resolved_entity(fact))
            elif fact.module_name and (fact.module_name == q_clean or fact.module_name.endswith(f".{q_clean}")):
                matching_paths.append(self._to_resolved_entity(fact))

        if len(matching_paths) == 1:
            return EntityResolutionResult(
                query_string=q_clean,
                status=EntityResolutionStatus.RESOLVED,
                entity=matching_paths[0],
                candidates=matching_paths,
                message=f"Unambiguous module/file match for '{q_clean}' -> '{matching_paths[0].qualified_name}'.",
            )
        elif len(matching_paths) > 1:
            return EntityResolutionResult(
                query_string=q_clean,
                status=EntityResolutionStatus.AMBIGUOUS,
                entity=None,
                candidates=sorted(matching_paths, key=lambda e: e.qualified_name),
                message=(
                    f"Ambiguous path match '{q_clean}' matched {len(matching_paths)} entities: "
                    f"{', '.join(e.qualified_name for e in matching_paths)}."
                ),
            )

        # 5. Not Found
        return EntityResolutionResult(
            query_string=q_clean,
            status=EntityResolutionStatus.NOT_FOUND,
            entity=None,
            candidates=[],
            message=f"Entity '{q_clean}' not found in snapshot '{self.snapshot_id}' of repository '{self.repository_id}'.",
        )

    def _to_resolved_entity(self, fact: SnapshotEntityFact) -> ResolvedEntity:
        return ResolvedEntity(
            canonical_id=fact.qualified_name,
            qualified_name=fact.qualified_name,
            entity_kind=fact.entity_kind,
            repository_id=self.repository_id,
            snapshot_id=self.snapshot_id,
            module_name=fact.module_name,
            file_path=fact.file_path,
            architecture_role=fact.architecture_role,
            architecture_layer=fact.architecture_layer,
            confidence=ResolutionConfidence.EXACT,
        )
