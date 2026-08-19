import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func
from archon.models.repository import AnalysisSnapshot
from archon.models.metrics import EntityMetric
from archon.models.evolution import (
    SnapshotMetadata, SnapshotComparison, TimelineNode, 
    EntityLifecycle, EntityLifecycleState, MetricDelta, MetricTrend,
    RelationshipChange, DriftFinding, DriftSeverity
)
from archon.db.neo4j import neo4j_driver
import logging

logger = logging.getLogger(__name__)

class EvolutionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _calculate_trend(self, values: List[float]) -> MetricTrend:
        if not values or len(values) < 2:
            return MetricTrend.UNKNOWN
        
        deltas = [values[i] - values[i-1] for i in range(1, len(values))]
        if all(d > 0 for d in deltas):
            return MetricTrend.INCREASING
        if all(d < 0 for d in deltas):
            return MetricTrend.DECREASING
        if all(d == 0 for d in deltas):
            return MetricTrend.STABLE
        return MetricTrend.VOLATILE

    async def get_timeline(self, repository_id: uuid.UUID) -> List[TimelineNode]:
        """Returns a chronological list of snapshots and their aggregated metrics."""
        result = await self.db.execute(
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.repository_id == repository_id)
            .order_by(asc(AnalysisSnapshot.analyzed_at))
        )
        snapshots = result.scalars().all()
        
        timeline = []
        for snap in snapshots:
            # Aggregate metrics for this snapshot
            metrics_res = await self.db.execute(
                select(EntityMetric.entity_type, EntityMetric.metric_name, EntityMetric.metric_value)
                .where(EntityMetric.snapshot_id == snap.id)
            )
            
            total_files = 0
            total_funcs = 0
            comp_sum = 0.0
            comp_count = 0
            coup_sum = 0.0
            coup_count = 0
            repo_risk = 0.0
            
            # Simple aggregation
            for m_type, m_name, m_val in metrics_res:
                if m_type == "File" and m_name == "churn": # Proxy for files existing if we don't have file counts explicitly as a metric
                    pass
                if m_type == "Repository" and m_name == "risk_score":
                    repo_risk = float(m_val)
                if m_type == "Function" and m_name == "cyclomatic_complexity":
                    total_funcs += 1
                    comp_sum += float(m_val)
                    comp_count += 1
                if m_type == "File" and m_name == "normalized_complexity":
                    total_files += 1
                if m_type == "Module" and m_name == "outgoing_coupling":
                    coup_sum += float(m_val)
                    coup_count += 1
                    
            timeline.append(TimelineNode(
                snapshot_id=snap.id,
                analyzed_at=snap.analyzed_at,
                commit_sha=snap.commit_sha,
                total_files=total_files,
                total_functions=total_funcs,
                average_complexity=(comp_sum / comp_count) if comp_count > 0 else 0.0,
                average_coupling=(coup_sum / coup_count) if coup_count > 0 else 0.0,
                repository_risk=repo_risk
            ))
            
        return timeline

    async def compare_snapshots(
        self, repository_id: uuid.UUID, previous_snapshot_id: uuid.UUID, current_snapshot_id: uuid.UUID
    ) -> SnapshotComparison:
        # Validate snapshots
        prev_res = await self.db.execute(
            select(AnalysisSnapshot).where(
                and_(AnalysisSnapshot.id == previous_snapshot_id, AnalysisSnapshot.repository_id == repository_id)
            )
        )
        prev_snap = prev_res.scalars().first()
        
        curr_res = await self.db.execute(
            select(AnalysisSnapshot).where(
                and_(AnalysisSnapshot.id == current_snapshot_id, AnalysisSnapshot.repository_id == repository_id)
            )
        )
        curr_snap = curr_res.scalars().first()
        
        if not prev_snap or not curr_snap:
            raise ValueError("Snapshots not found or do not belong to the given repository")
            
        comp = SnapshotComparison(
            repository_id=repository_id,
            previous_snapshot=SnapshotMetadata(snapshot_id=prev_snap.id, analyzed_at=prev_snap.analyzed_at, commit_sha=prev_snap.commit_sha),
            current_snapshot=SnapshotMetadata(snapshot_id=curr_snap.id, analyzed_at=curr_snap.analyzed_at, commit_sha=curr_snap.commit_sha)
        )
        
        # 1. Compare Metrics (Postgres)
        prev_metrics_res = await self.db.execute(
            select(EntityMetric).where(EntityMetric.snapshot_id == previous_snapshot_id)
        )
        prev_metrics = prev_metrics_res.scalars().all()
        
        curr_metrics_res = await self.db.execute(
            select(EntityMetric).where(EntityMetric.snapshot_id == current_snapshot_id)
        )
        curr_metrics = curr_metrics_res.scalars().all()
        
        # Group metrics by entity
        prev_entities: Dict[str, Dict[str, Any]] = {}
        for m in prev_metrics:
            key = f"{m.entity_type}:{m.entity_name}"
            if key not in prev_entities:
                prev_entities[key] = {"type": m.entity_type, "name": m.entity_name, "metrics": {}}
            prev_entities[key]["metrics"][m.metric_name] = float(m.metric_value)
            
        curr_entities: Dict[str, Dict[str, Any]] = {}
        for m in curr_metrics:
            key = f"{m.entity_type}:{m.entity_name}"
            if key not in curr_entities:
                curr_entities[key] = {"type": m.entity_type, "name": m.entity_name, "metrics": {}}
            curr_entities[key]["metrics"][m.metric_name] = float(m.metric_value)
            
        all_keys = set(prev_entities.keys()) | set(curr_entities.keys())
        
        for key in all_keys:
            prev_e = prev_entities.get(key)
            curr_e = curr_entities.get(key)
            
            if prev_e and not curr_e:
                state = EntityLifecycleState.REMOVED
                e_type = prev_e["type"]
                qname = prev_e["name"]
                m_curr = {}
                m_prev = prev_e["metrics"]
            elif not prev_e and curr_e:
                state = EntityLifecycleState.ADDED
                e_type = curr_e["type"]
                qname = curr_e["name"]
                m_curr = curr_e["metrics"]
                m_prev = {}
            else:
                e_type = curr_e["type"]
                qname = curr_e["name"]
                m_curr = curr_e["metrics"]
                m_prev = prev_e["metrics"]
                if m_curr == m_prev:
                    state = EntityLifecycleState.UNCHANGED
                else:
                    state = EntityLifecycleState.MODIFIED
                    
            lifecycle = EntityLifecycle(
                entity_type=e_type,
                qualified_name=qname,
                state=state
            )
            
            all_metric_names = set(m_curr.keys()) | set(m_prev.keys())
            for m_name in all_metric_names:
                p_val = m_prev.get(m_name)
                c_val = m_curr.get(m_name)
                
                delta = None
                pct_change = None
                if p_val is not None and c_val is not None:
                    delta = c_val - p_val
                    if p_val != 0:
                        pct_change = delta / abs(p_val)
                        
                lifecycle.metrics[m_name] = MetricDelta(
                    metric_name=m_name,
                    previous_value=p_val,
                    current_value=c_val,
                    delta=delta,
                    percentage_change=pct_change
                )
                
            comp.entities.append(lifecycle)
            
        # 2. Compare Relationships (Neo4j)
        async with neo4j_driver.session() as session:
            # Get dependencies from previous snapshot
            query = """
            MATCH (s {snapshot_id: $snap_id})-[r]->(t {snapshot_id: $snap_id})
            WHERE type(r) IN ['CALLS', 'IMPORTS', 'DEPENDS_ON']
            RETURN s.qualified_name as source, type(r) as rel_type, t.qualified_name as target, r.resolution as res
            """
            prev_rels_res = await session.run(query, snap_id=str(previous_snapshot_id))
            prev_rels = {f"{r['source']}:{r['rel_type']}:{r['target']}": r["res"] for r in await prev_rels_res.data()}
            
            curr_rels_res = await session.run(query, snap_id=str(current_snapshot_id))
            curr_rels = {f"{r['source']}:{r['rel_type']}:{r['target']}": r["res"] for r in await curr_rels_res.data()}
            
            all_rel_keys = set(prev_rels.keys()) | set(curr_rels.keys())
            for r_key in all_rel_keys:
                source, rel_type, target = r_key.split(":")
                p_res = prev_rels.get(r_key)
                c_res = curr_rels.get(r_key)
                
                if r_key in prev_rels and r_key not in curr_rels:
                    comp.relationships.append(RelationshipChange(
                        source_qname=source, target_qname=target, relationship_type=rel_type,
                        state=EntityLifecycleState.REMOVED, previous_resolution=p_res
                    ))
                elif r_key not in prev_rels and r_key in curr_rels:
                    comp.relationships.append(RelationshipChange(
                        source_qname=source, target_qname=target, relationship_type=rel_type,
                        state=EntityLifecycleState.ADDED, current_resolution=c_res
                    ))
                else:
                    if p_res != c_res:
                        comp.relationships.append(RelationshipChange(
                            source_qname=source, target_qname=target, relationship_type=rel_type,
                            state=EntityLifecycleState.MODIFIED, previous_resolution=p_res, current_resolution=c_res
                        ))
                        
        # 3. Calculate Archon Architecture Drift Heuristic v1
        for entity in comp.entities:
            if entity.entity_type == "Module" and entity.state in (EntityLifecycleState.MODIFIED, EntityLifecycleState.UNCHANGED):
                risk_metric = entity.metrics.get("risk_score")
                if risk_metric and risk_metric.percentage_change and risk_metric.percentage_change > 0.10:
                    # Check if it gained dependencies
                    gained_deps = [r for r in comp.relationships if r.source_qname == entity.qualified_name and r.state == EntityLifecycleState.ADDED and r.relationship_type in ('IMPORTS', 'DEPENDS_ON')]
                    if gained_deps:
                        targets = ", ".join([d.target_qname for d in gained_deps])
                        comp.drift_findings.append(DriftFinding(
                            severity=DriftSeverity.HIGH,
                            entity_name=entity.qualified_name,
                            entity_type="Module",
                            reason=f"Module gained new dependencies ({targets}) and risk increased significantly (+{risk_metric.percentage_change*100:.1f}%)."
                        ))
        
        async with neo4j_driver.session() as session:
            cycles_q = """
            MATCH (m:Module {snapshot_id: $snap_id})
            MATCH path = (m)-[:DEPENDS_ON*1..5]->(m)
            RETURN m.qualified_name as qname
            """
            p_cycles_res = await session.run(cycles_q, snap_id=str(previous_snapshot_id))
            p_cycles = {r["qname"] for r in await p_cycles_res.data()}
            
            c_cycles_res = await session.run(cycles_q, snap_id=str(current_snapshot_id))
            c_cycles = {r["qname"] for r in await c_cycles_res.data()}
            
            new_cycles = c_cycles - p_cycles
            for c in new_cycles:
                comp.drift_findings.append(DriftFinding(
                    severity=DriftSeverity.MODERATE,
                    entity_name=c,
                    entity_type="Module",
                    reason="A new circular dependency was introduced involving this module."
                ))
                
        return comp
