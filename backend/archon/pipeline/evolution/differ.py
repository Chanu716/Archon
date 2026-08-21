"""
Deterministic Snapshot Differ (Slice ML-12)

Compares baseline and target snapshots to extract:
  - Added, removed, modified, and unchanged entities using canonical identity.
  - Added, removed, and unchanged directional relationships.
  - Relationship resolution confidence improvements and degradations.

Guarantees:
  - Snapshot & repository isolation.
  - Zero speculative rename detection (removed + added remain separate facts).
  - Line numbers are NOT used as primary identity.
"""

from typing import List, Dict, Set, Tuple, Optional
import structlog

from archon.pipeline.evolution.models import (
    ChangeType,
    SnapshotEntityFact,
    SnapshotRelationshipFact,
    EntityDiff,
    RelationshipDiff,
    SnapshotDiffResult,
)

logger = structlog.get_logger(__name__)


class SnapshotDiffer:
    """
    Computes deterministic structural and relational diffs between two snapshots.
    """

    def __init__(self, repository_id: str, baseline_snapshot_id: str, target_snapshot_id: str):
        self.repository_id = str(repository_id)
        self.baseline_snapshot_id = str(baseline_snapshot_id)
        self.target_snapshot_id = str(target_snapshot_id)

    def diff_snapshots(
        self,
        baseline_entities: Dict[str, SnapshotEntityFact],
        target_entities: Dict[str, SnapshotEntityFact],
        baseline_relationships: List[SnapshotRelationshipFact],
        target_relationships: List[SnapshotRelationshipFact],
    ) -> SnapshotDiffResult:
        # 1. Entity Diffs
        entity_diffs: Dict[str, EntityDiff] = {}
        added_entities: List[str] = []
        removed_entities: List[str] = []
        modified_entities: List[str] = []

        all_entity_keys = sorted(set(baseline_entities.keys()) | set(target_entities.keys()))

        for qname in all_entity_keys:
            base_ent = baseline_entities.get(qname)
            tgt_ent = target_entities.get(qname)

            if base_ent is None and tgt_ent is not None:
                # Entity Added
                entity_diffs[qname] = EntityDiff(
                    qualified_name=qname,
                    entity_kind=tgt_ent.entity_kind,
                    change_type=ChangeType.ADDED,
                    baseline_entity=None,
                    target_entity=tgt_ent,
                )
                added_entities.append(qname)

            elif base_ent is not None and tgt_ent is None:
                # Entity Removed
                entity_diffs[qname] = EntityDiff(
                    qualified_name=qname,
                    entity_kind=base_ent.entity_kind,
                    change_type=ChangeType.REMOVED,
                    baseline_entity=base_ent,
                    target_entity=None,
                )
                removed_entities.append(qname)

            elif base_ent is not None and tgt_ent is not None:
                # Entity in both — check for field differences
                field_changes: Dict[str, Tuple[Any, Any]] = {}

                if base_ent.architecture_role != tgt_ent.architecture_role:
                    field_changes["architecture_role"] = (base_ent.architecture_role, tgt_ent.architecture_role)
                if base_ent.architecture_layer != tgt_ent.architecture_layer:
                    field_changes["architecture_layer"] = (base_ent.architecture_layer, tgt_ent.architecture_layer)
                if base_ent.file_path != tgt_ent.file_path:
                    field_changes["file_path"] = (base_ent.file_path, tgt_ent.file_path)

                if field_changes:
                    entity_diffs[qname] = EntityDiff(
                        qualified_name=qname,
                        entity_kind=tgt_ent.entity_kind,
                        change_type=ChangeType.MODIFIED,
                        baseline_entity=base_ent,
                        target_entity=tgt_ent,
                        field_changes=field_changes,
                    )
                    modified_entities.append(qname)
                else:
                    entity_diffs[qname] = EntityDiff(
                        qualified_name=qname,
                        entity_kind=tgt_ent.entity_kind,
                        change_type=ChangeType.UNCHANGED,
                        baseline_entity=base_ent,
                        target_entity=tgt_ent,
                    )

        # 2. Relationship Diffs
        base_rel_map: Dict[str, SnapshotRelationshipFact] = {r.canonical_id: r for r in baseline_relationships}
        tgt_rel_map: Dict[str, SnapshotRelationshipFact] = {r.canonical_id: r for r in target_relationships}

        relationship_diffs: Dict[str, RelationshipDiff] = {}
        added_relationships: List[str] = []
        removed_relationships: List[str] = []
        resolution_changes: List[RelationshipDiff] = []

        all_rel_keys = sorted(set(base_rel_map.keys()) | set(tgt_rel_map.keys()))

        for rel_key in all_rel_keys:
            b_rel = base_rel_map.get(rel_key)
            t_rel = tgt_rel_map.get(rel_key)

            if b_rel is None and t_rel is not None:
                # Relationship Added
                relationship_diffs[rel_key] = RelationshipDiff(
                    canonical_id=rel_key,
                    source_id=t_rel.source_id,
                    relationship_type=t_rel.relationship_type,
                    target_id=t_rel.target_id,
                    change_type=ChangeType.ADDED,
                    baseline_rel=None,
                    target_rel=t_rel,
                )
                added_relationships.append(rel_key)

            elif b_rel is not None and t_rel is None:
                # Relationship Removed
                relationship_diffs[rel_key] = RelationshipDiff(
                    canonical_id=rel_key,
                    source_id=b_rel.source_id,
                    relationship_type=b_rel.relationship_type,
                    target_id=b_rel.target_id,
                    change_type=ChangeType.REMOVED,
                    baseline_rel=b_rel,
                    target_rel=None,
                )
                removed_relationships.append(rel_key)

            elif b_rel is not None and t_rel is not None:
                # Relationship in both — check resolution change
                res_change = None
                if b_rel.resolution != t_rel.resolution:
                    res_change = (b_rel.resolution, t_rel.resolution)

                diff = RelationshipDiff(
                    canonical_id=rel_key,
                    source_id=t_rel.source_id,
                    relationship_type=t_rel.relationship_type,
                    target_id=t_rel.target_id,
                    change_type=ChangeType.UNCHANGED,
                    baseline_rel=b_rel,
                    target_rel=t_rel,
                    resolution_change=res_change,
                )
                relationship_diffs[rel_key] = diff
                if res_change:
                    resolution_changes.append(diff)

        logger.info(
            "snapshot_diff_completed",
            added_entities=len(added_entities),
            removed_entities=len(removed_entities),
            modified_entities=len(modified_entities),
            added_relationships=len(added_relationships),
            removed_relationships=len(removed_relationships),
            resolution_changes=len(resolution_changes),
            baseline_id=self.baseline_snapshot_id,
            target_id=self.target_snapshot_id,
        )

        return SnapshotDiffResult(
            repository_id=self.repository_id,
            baseline_snapshot_id=self.baseline_snapshot_id,
            target_snapshot_id=self.target_snapshot_id,
            entity_diffs=entity_diffs,
            relationship_diffs=relationship_diffs,
            added_entities=added_entities,
            removed_entities=removed_entities,
            modified_entities=modified_entities,
            added_relationships=added_relationships,
            removed_relationships=removed_relationships,
            resolution_changes=resolution_changes,
        )
