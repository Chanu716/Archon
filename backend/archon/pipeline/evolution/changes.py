"""
Architecture Change Analyzer (Slice ML-12)

Translates raw snapshot diffs into semantic architectural changes:
  - Role modifications (e.g. Service -> Repository)
  - Layer transitions (e.g. Application -> Infrastructure)
  - Dependency additions and removals (DEPENDS_ON, IMPLEMENTS, CALLS, IMPORTS)
  - HTTP Endpoint lifecycle changes (Endpoints added/removed, Handlers reassigned)
  - Relationship resolution improvements and degradations
"""

from typing import List, Dict, Optional, Any
import structlog

from archon.pipeline.evolution.models import (
    ChangeType,
    SnapshotDiffResult,
    ArchitectureChangeFact,
)

logger = structlog.get_logger(__name__)

RESOLUTION_RANK = {
    "unresolved": 0,
    "inferred": 1,
    "exact": 2,
}


class ArchitectureChangeAnalyzer:
    """
    Analyzes semantic architectural changes from snapshot diff results.
    """

    def __init__(self, repository_id: str, baseline_snapshot_id: str, target_snapshot_id: str):
        self.repository_id = str(repository_id)
        self.baseline_snapshot_id = str(baseline_snapshot_id)
        self.target_snapshot_id = str(target_snapshot_id)

    def analyze_changes(self, diff: SnapshotDiffResult) -> List[ArchitectureChangeFact]:
        changes: List[ArchitectureChangeFact] = []

        # 1. Entity Role and Layer Changes
        for qname, ediff in diff.entity_diffs.items():
            if ediff.change_type == ChangeType.MODIFIED:
                if "architecture_role" in ediff.field_changes:
                    old_role, new_role = ediff.field_changes["architecture_role"]
                    changes.append(ArchitectureChangeFact(
                        change_id=f"role_change:{qname}:{old_role}->{new_role}",
                        category="role_change",
                        entity_id=qname,
                        description=f"Architectural role of '{qname}' changed from '{old_role}' to '{new_role}'",
                        old_value=old_role,
                        new_value=new_role,
                        repository_id=self.repository_id,
                        baseline_snapshot_id=self.baseline_snapshot_id,
                        target_snapshot_id=self.target_snapshot_id,
                    ))

                if "architecture_layer" in ediff.field_changes:
                    old_layer, new_layer = ediff.field_changes["architecture_layer"]
                    changes.append(ArchitectureChangeFact(
                        change_id=f"layer_change:{qname}:{old_layer}->{new_layer}",
                        category="layer_change",
                        entity_id=qname,
                        description=f"Architectural layer of '{qname}' changed from '{old_layer}' to '{new_layer}'",
                        old_value=old_layer,
                        new_value=new_layer,
                        repository_id=self.repository_id,
                        baseline_snapshot_id=self.baseline_snapshot_id,
                        target_snapshot_id=self.target_snapshot_id,
                    ))

            elif ediff.change_type == ChangeType.ADDED and ediff.entity_kind == "Endpoint":
                changes.append(ArchitectureChangeFact(
                    change_id=f"endpoint_added:{qname}",
                    category="endpoint_added",
                    entity_id=qname,
                    description=f"New HTTP endpoint added: '{qname}'",
                    old_value=None,
                    new_value=qname,
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                ))

            elif ediff.change_type == ChangeType.REMOVED and ediff.entity_kind == "Endpoint":
                changes.append(ArchitectureChangeFact(
                    change_id=f"endpoint_removed:{qname}",
                    category="endpoint_removed",
                    entity_id=qname,
                    description=f"HTTP endpoint removed: '{qname}'",
                    old_value=qname,
                    new_value=None,
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                ))

        # 2. Relationship Changes
        for rel_key, rdiff in diff.relationship_diffs.items():
            if rdiff.change_type == ChangeType.ADDED:
                category = f"dependency_added:{rdiff.relationship_type.lower()}"
                changes.append(ArchitectureChangeFact(
                    change_id=f"rel_added:{rdiff.canonical_id}",
                    category=category,
                    entity_id=rdiff.source_id,
                    description=f"Added {rdiff.relationship_type} relationship: '{rdiff.source_id}' -> '{rdiff.target_id}'",
                    old_value=None,
                    new_value=rdiff.target_id,
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                    metadata={"target_id": rdiff.target_id, "relationship_type": rdiff.relationship_type}
                ))

            elif rdiff.change_type == ChangeType.REMOVED:
                category = f"dependency_removed:{rdiff.relationship_type.lower()}"
                changes.append(ArchitectureChangeFact(
                    change_id=f"rel_removed:{rdiff.canonical_id}",
                    category=category,
                    entity_id=rdiff.source_id,
                    description=f"Removed {rdiff.relationship_type} relationship: '{rdiff.source_id}' -> '{rdiff.target_id}'",
                    old_value=rdiff.target_id,
                    new_value=None,
                    repository_id=self.repository_id,
                    baseline_snapshot_id=self.baseline_snapshot_id,
                    target_snapshot_id=self.target_snapshot_id,
                    metadata={"target_id": rdiff.target_id, "relationship_type": rdiff.relationship_type}
                ))

            elif rdiff.resolution_change:
                old_res, new_res = rdiff.resolution_change
                old_rank = RESOLUTION_RANK.get(old_res, 0)
                new_rank = RESOLUTION_RANK.get(new_res, 0)

                if new_rank > old_rank:
                    changes.append(ArchitectureChangeFact(
                        change_id=f"resolution_improved:{rdiff.canonical_id}",
                        category="resolution_improved",
                        entity_id=rdiff.source_id,
                        description=f"Resolution of {rdiff.relationship_type} to '{rdiff.target_id}' improved from '{old_res}' to '{new_res}'",
                        old_value=old_res,
                        new_value=new_res,
                        repository_id=self.repository_id,
                        baseline_snapshot_id=self.baseline_snapshot_id,
                        target_snapshot_id=self.target_snapshot_id,
                        metadata={"target_id": rdiff.target_id, "relationship_type": rdiff.relationship_type}
                    ))
                elif new_rank < old_rank:
                    changes.append(ArchitectureChangeFact(
                        change_id=f"resolution_degraded:{rdiff.canonical_id}",
                        category="resolution_degraded",
                        entity_id=rdiff.source_id,
                        description=f"Resolution of {rdiff.relationship_type} to '{rdiff.target_id}' degraded from '{old_res}' to '{new_res}'",
                        old_value=old_res,
                        new_value=new_res,
                        repository_id=self.repository_id,
                        baseline_snapshot_id=self.baseline_snapshot_id,
                        target_snapshot_id=self.target_snapshot_id,
                        metadata={"target_id": rdiff.target_id, "relationship_type": rdiff.relationship_type}
                    ))

        logger.info(
            "architecture_changes_analyzed",
            total_changes=len(changes),
            baseline_id=self.baseline_snapshot_id,
            target_id=self.target_snapshot_id,
        )
        return changes
