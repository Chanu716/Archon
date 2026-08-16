import uuid
import structlog
from typing import List, Dict, Any
from archon.db.neo4j import neo4j_driver
from archon.db.session import async_session_factory
from archon.models.metrics import EntityMetric

logger = structlog.get_logger(__name__)

class StaticAnalyzer:
    def __init__(self, repository_id: uuid.UUID, snapshot_id: uuid.UUID):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

    async def run_analysis(self):
        """Runs the static analysis metrics extraction."""
        logger.info("starting_static_analysis", snapshot_id=self.snapshot_id)
        
        metrics = []
        
        if not neo4j_driver.driver:
            neo4j_driver.connect()
            
        async with neo4j_driver.driver.session() as session:
            # 1. Function Level Metrics (Fan-in, Fan-out)
            # Fan-out: Number of unique functions this function calls (exact or inferred)
            # Fan-in: Number of unique functions that call this function (exact or inferred)
            
            fan_out_query = """
            MATCH (f:Function {snapshot_id: $snapshot_id})
            OPTIONAL MATCH (f)-[c:CALLS]->(t:Function {snapshot_id: $snapshot_id})
            WHERE c.resolution IN ['exact', 'inferred']
            WITH f, COUNT(DISTINCT t) as fan_out
            RETURN f.qualified_name as qname, fan_out, f.cyclomatic_complexity as cc
            """
            
            fan_in_query = """
            MATCH (f:Function {snapshot_id: $snapshot_id})
            OPTIONAL MATCH (caller:Function {snapshot_id: $snapshot_id})-[c:CALLS]->(f)
            WHERE c.resolution IN ['exact', 'inferred']
            WITH f, COUNT(DISTINCT caller) as fan_in
            RETURN f.qualified_name as qname, fan_in
            """
            
            result = await session.run(fan_out_query, snapshot_id=self.snapshot_id)
            records = await result.data()
            fan_out_map = {r["qname"]: {"fan_out": r["fan_out"], "cc": r["cc"]} for r in records}
            
            result = await session.run(fan_in_query, snapshot_id=self.snapshot_id)
            records = await result.data()
            for r in records:
                if r["qname"] in fan_out_map:
                    fan_out_map[r["qname"]]["fan_in"] = r["fan_in"]

            for qname, data in fan_out_map.items():
                metrics.append(EntityMetric(
                    snapshot_id=self.snapshot_id,
                    entity_type="Function",
                    entity_name=qname,
                    metric_name="fan_out",
                    metric_value=float(data.get("fan_out", 0)),
                    metric_source="deterministic"
                ))
                metrics.append(EntityMetric(
                    snapshot_id=self.snapshot_id,
                    entity_type="Function",
                    entity_name=qname,
                    metric_name="fan_in",
                    metric_value=float(data.get("fan_in", 0)),
                    metric_source="deterministic"
                ))
                metrics.append(EntityMetric(
                    snapshot_id=self.snapshot_id,
                    entity_type="Function",
                    entity_name=qname,
                    metric_name="cyclomatic_complexity",
                    metric_value=float(data.get("cc") or 0),
                    metric_source="deterministic"
                ))
                
            # 2. Module Level Metrics (Coupling, Cycles)
            # Incoming Coupling (Dependencies on this module)
            in_coupling_query = """
            MATCH (m:Module {snapshot_id: $snapshot_id})
            OPTIONAL MATCH (other:Module {snapshot_id: $snapshot_id})-[:IMPORTS]->(m)
            WHERE other <> m
            WITH m, COUNT(DISTINCT other) as incoming_coupling
            RETURN m.qualified_name as qname, incoming_coupling
            """
            
            # Outgoing Coupling (Dependencies this module has)
            out_coupling_query = """
            MATCH (m:Module {snapshot_id: $snapshot_id})
            OPTIONAL MATCH (m)-[:IMPORTS]->(other:Module {snapshot_id: $snapshot_id})
            WHERE other <> m
            WITH m, COUNT(DISTINCT other) as outgoing_coupling
            RETURN m.qualified_name as qname, outgoing_coupling
            """
            
            result = await session.run(in_coupling_query, snapshot_id=self.snapshot_id)
            records = await result.data()
            coupling_map = {r["qname"]: {"incoming_coupling": r["incoming_coupling"]} for r in records}
            
            result = await session.run(out_coupling_query, snapshot_id=self.snapshot_id)
            records = await result.data()
            for r in records:
                if r["qname"] in coupling_map:
                    coupling_map[r["qname"]]["outgoing_coupling"] = r["outgoing_coupling"]
                    
            for qname, data in coupling_map.items():
                metrics.append(EntityMetric(
                    snapshot_id=self.snapshot_id,
                    entity_type="Module",
                    entity_name=qname,
                    metric_name="incoming_coupling",
                    metric_value=float(data.get("incoming_coupling", 0)),
                    metric_source="deterministic"
                ))
                metrics.append(EntityMetric(
                    snapshot_id=self.snapshot_id,
                    entity_type="Module",
                    entity_name=qname,
                    metric_name="outgoing_coupling",
                    metric_value=float(data.get("outgoing_coupling", 0)),
                    metric_source="deterministic"
                ))
                
            # 3. Circular Dependencies
            # We look for simple cycles of length up to 5 for architectural health
            cycles_query = """
            MATCH (m:Module {snapshot_id: $snapshot_id})
            MATCH path = (m)-[:IMPORTS*1..5]->(m)
            RETURN m.qualified_name as qname, count(path) as cycle_count
            """
            result = await session.run(cycles_query, snapshot_id=self.snapshot_id)
            records = await result.data()
            
            cycle_counts = {}
            for r in records:
                qname = r["qname"]
                cycle_counts[qname] = r["cycle_count"]
                
            for qname, count in cycle_counts.items():
                metrics.append(EntityMetric(
                    snapshot_id=self.snapshot_id,
                    entity_type="Module",
                    entity_name=qname,
                    metric_name="circular_dependencies",
                    metric_value=float(count),
                    metric_source="deterministic"
                ))
                
        # 4. Archon Risk Heuristic v1 (Option A: Normalized without Churn)
        # Normalize complexity and coupling (0 to 1) and calculate partial score
        self._calculate_risk_heuristics(metrics, fan_out_map, coupling_map)
        
        # 5. Persist to Postgres
        await self._persist_metrics(metrics)
        logger.info("static_analysis_complete", metrics_count=len(metrics))

    def _calculate_risk_heuristics(self, metrics: List[EntityMetric], fan_out_map: dict, coupling_map: dict):
        """Calculates normalized partial complexity and coupling scores.
        
        Normalization method: Max-normalization (value / max_value).
        This is NOT min-max scaling; it does not subtract the minimum.
        
        Formula: normalized_value = value / max_value
        Edge cases: 
          - If max_value == 0 (all values are zero), normalized values are 0.
          - Empty repositories return no metrics.
        
        metric_source = 'deterministic' because normalization is a deterministic
        mathematical transformation of deterministic input metrics.
        
        NOTE: The final Archon Risk Heuristic v1 score (which combines complexity,
        coupling, and Git churn) is intentionally NOT calculated here.
        It will be implemented in Slice 5 once Git churn is available.
        At that point, the composite risk score will carry metric_source = 'archon_heuristic_v1'.
        """
        if not fan_out_map and not coupling_map:
            return
            
        max_cc = max((d.get("cc") or 0 for d in fan_out_map.values()), default=1)
        if max_cc == 0: max_cc = 1  # Prevent division by zero
        
        max_coupling = max((d.get("outgoing_coupling") or 0 for d in coupling_map.values()), default=1)
        if max_coupling == 0: max_coupling = 1  # Prevent division by zero
        
        # Max-normalization: normalized_value = value / max_value (not min-max)
        # These are deterministic transformations, so metric_source = 'deterministic'
        for qname, data in fan_out_map.items():
            norm_cc = (data.get("cc") or 0) / max_cc
            metrics.append(EntityMetric(
                snapshot_id=self.snapshot_id,
                entity_type="Function",
                entity_name=qname,
                metric_name="normalized_complexity",
                metric_value=float(norm_cc),
                metric_source="deterministic"
            ))
            
        for qname, data in coupling_map.items():
            norm_coupling = (data.get("outgoing_coupling") or 0) / max_coupling
            metrics.append(EntityMetric(
                snapshot_id=self.snapshot_id,
                entity_type="Module",
                entity_name=qname,
                metric_name="normalized_coupling",
                metric_value=float(norm_coupling),
                metric_source="deterministic"
            ))

    async def _persist_metrics(self, metrics: List[EntityMetric]):
        async with async_session_factory() as db:
            db.add_all(metrics)
            await db.commit()
