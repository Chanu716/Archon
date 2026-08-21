"""
Change Impact & Risk Analyzer (Slice ML-12)

Computes:
  1. Direct and transitive architectural blast radius of changed components.
  2. Direction-explicit, depth-bounded, and cycle-safe impact traversal.
  3. Transparent, rule-based, explainable Change Risk Classification (High, Medium, Low).
"""

from typing import List, Dict, Set, Tuple, Optional
import structlog

from archon.pipeline.evolution.models import (
    ChangeType,
    RiskLevel,
    ChangeImpactFact,
    ChangeRiskFact,
    SnapshotDiffResult,
    ArchitectureRegression,
    RegressionType,
)
from archon.pipeline.architecture.models import ArchitectureAnalysisResult

logger = structlog.get_logger(__name__)

MAX_IMPACT_DEPTH = 5


class ChangeImpactAnalyzer:
    """
    Computes architectural blast radius and explainable change risk.
    """

    def __init__(self, repository_id: str, baseline_snapshot_id: str, target_snapshot_id: str, max_depth: int = MAX_IMPACT_DEPTH):
        self.repository_id = str(repository_id)
        self.baseline_snapshot_id = str(baseline_snapshot_id)
        self.target_snapshot_id = str(target_snapshot_id)
        self.max_depth = max_depth

    def analyze_impact_and_risk(
        self,
        diff: SnapshotDiffResult,
        regressions: List[ArchitectureRegression],
        target_arch: Optional[ArchitectureAnalysisResult],
    ) -> Tuple[List[ChangeImpactFact], ChangeRiskFact]:
        # 1. Build adjacency maps for target snapshot
        inbound_adj: Dict[str, Set[str]] = {}
        outbound_adj: Dict[str, Set[str]] = {}

        for rdiff in diff.relationship_diffs.values():
            if rdiff.target_rel:
                u, v = rdiff.source_id, rdiff.target_id
                outbound_adj.setdefault(u, set()).add(v)
                inbound_adj.setdefault(v, set()).add(u)

        # 2. Collect all directly changed entities
        changed_entities = sorted(set(diff.added_entities) | set(diff.removed_entities) | set(diff.modified_entities))

        impact_facts: List[ChangeImpactFact] = []

        for entity in changed_entities:
            direct_dependents = sorted(inbound_adj.get(entity, set()))
            direct_dependencies = sorted(outbound_adj.get(entity, set()))

            # Bounded transitive traversal (Upstream dependents + Downstream dependencies)
            transitive_visited: Set[str] = set()
            queue: List[Tuple[str, int]] = [(entity, 0)]
            visited_in_traversal: Set[str] = {entity}

            while queue:
                curr, depth = queue.pop(0)
                if depth < self.max_depth:
                    # Upstream
                    for up in inbound_adj.get(curr, set()):
                        if up not in visited_in_traversal:
                            visited_in_traversal.add(up)
                            transitive_visited.add(up)
                            queue.append((up, depth + 1))
                    # Downstream
                    for down in outbound_adj.get(curr, set()):
                        if down not in visited_in_traversal:
                            visited_in_traversal.add(down)
                            transitive_visited.add(down)
                            queue.append((down, depth + 1))

            blast_radius = len(direct_dependents) + len(direct_dependencies) + len(transitive_visited)

            impact_facts.append(ChangeImpactFact(
                changed_entity=entity,
                direct_dependents=direct_dependents,
                direct_dependencies=direct_dependencies,
                transitive_impacted_nodes=sorted(transitive_visited),
                impact_depth=min(self.max_depth, len(transitive_visited)),
                blast_radius_score=blast_radius,
            ))

        # 3. Transparent, Rule-Based Change Risk Evaluation
        risk_fact = self._evaluate_change_risk(diff, regressions, impact_facts, target_arch)

        return impact_facts, risk_fact

    def _evaluate_change_risk(
        self,
        diff: SnapshotDiffResult,
        regressions: List[ArchitectureRegression],
        impact_facts: List[ChangeImpactFact],
        target_arch: Optional[ArchitectureAnalysisResult],
    ) -> ChangeRiskFact:
        reasons: List[str] = []
        high_factors: List[str] = []
        med_factors: List[str] = []
        score = 0

        # High Risk Rules:
        # Rule 1: Introduced a new cycle
        new_cycles = [r for r in regressions if r.regression_type == RegressionType.NEW_CYCLE]
        if new_cycles:
            msg = f"Introduced {len(new_cycles)} new circular dependency cycle(s)"
            high_factors.append(msg)
            reasons.append(msg)
            score += 40

        # Rule 2: Introduced a new architecture violation
        new_viols = [r for r in regressions if r.regression_type == RegressionType.NEW_ARCHITECTURE_VIOLATION]
        if new_viols:
            msg = f"Introduced {len(new_viols)} new architectural violation(s)"
            high_factors.append(msg)
            reasons.append(msg)
            score += 35

        # Rule 3: Removed an entity with high dependents
        for removed in diff.removed_entities:
            # Check baseline dependents if available
            base_dep_count = sum(1 for r in diff.relationship_diffs.values() if r.target_id == removed and r.baseline_rel)
            if base_dep_count >= 2:
                msg = f"Removed heavily depended-on component '{removed}' ({base_dep_count} dependents)"
                high_factors.append(msg)
                reasons.append(msg)
                score += 30

        # Medium Risk Rules:
        # Rule 4: Hotspot growth
        hotspot_regressions = [r for r in regressions if r.regression_type == RegressionType.HOTSPOT_GROWTH]
        if hotspot_regressions:
            msg = f"Materially increased coupling on {len(hotspot_regressions)} dependency hotspot(s)"
            med_factors.append(msg)
            reasons.append(msg)
            score += 20

        # Rule 5: Dependency growth
        dep_growths = [r for r in regressions if r.regression_type == RegressionType.DEPENDENCY_GROWTH]
        if dep_growths:
            msg = f"Significant dependency coupling growth in {len(dep_growths)} component(s)"
            med_factors.append(msg)
            reasons.append(msg)
            score += 15

        # Rule 6: Resolution regressions (exact -> unresolved/inferred)
        res_regs = [r for r in regressions if r.regression_type == RegressionType.RESOLUTION_REGRESSION]
        if res_regs:
            msg = f"Resolution confidence degraded on {len(res_regs)} architectural relationship(s)"
            med_factors.append(msg)
            reasons.append(msg)
            score += 15

        # Rule 7: Role or Layer changes
        layer_modifications = [
            e for e in diff.entity_diffs.values()
            if e.change_type == ChangeType.MODIFIED and "architecture_layer" in e.field_changes
        ]
        if layer_modifications:
            msg = f"Architectural layer changed for {len(layer_modifications)} component(s)"
            med_factors.append(msg)
            reasons.append(msg)
            score += 10

        # Determine Final Level
        if high_factors or score >= 30:
            level = RiskLevel.HIGH
        elif med_factors or score >= 10:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW
            if not reasons:
                reasons.append("Low-risk isolated architectural modification with zero detected regressions.")

        return ChangeRiskFact(
            risk_level=level,
            score=min(100, score),
            reasons=reasons,
            high_risk_factors=high_factors,
            medium_risk_factors=med_factors,
            repository_id=self.repository_id,
            baseline_snapshot_id=self.baseline_snapshot_id,
            target_snapshot_id=self.target_snapshot_id,
        )
