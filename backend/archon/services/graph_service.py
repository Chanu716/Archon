import uuid
from typing import List, Dict, Any, Optional
from archon.db.neo4j import neo4j_driver
import structlog

logger = structlog.get_logger(__name__)

class GraphService:
    def __init__(self, repository_id: uuid.UUID, snapshot_id: uuid.UUID):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)

    async def get_overview(self) -> Dict[str, Any]:
        """Returns the top-level bounded graph view: Repositories, Files, and Modules.
        
        Node labels actually present in the Archon graph schema:
          Repository, File, Module, Class, Function
        Note: 'Directory' is NOT a valid label in the Archon graph.
        """
        query = """
        MATCH (n {snapshot_id: $snapshot_id})
        WHERE n:Repository OR n:File OR n:Module
        OPTIONAL MATCH (n)-[r]->(m {snapshot_id: $snapshot_id})
        WHERE m:Repository OR m:File OR m:Module
        RETURN n, r, m
        """
        return await self._execute_and_format(query)

    async def search_nodes(self, q: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Searches for nodes by qualified name or path."""
        query = """
        MATCH (n {snapshot_id: $snapshot_id})
        WHERE (n.qualified_name CONTAINS $q OR n.name CONTAINS $q OR n.path CONTAINS $q)
        AND NOT n:Repository
        RETURN n LIMIT $limit
        """
        if not neo4j_driver.driver:
            neo4j_driver.connect()
        async with neo4j_driver.driver.session() as session:
            result = await session.run(query, snapshot_id=self.snapshot_id, q=q, limit=limit)
            records = await result.data()
            return [self._format_node(r["n"]) for r in records]

    async def get_node_details(self, node_id: str) -> Dict[str, Any]:
        """Gets detailed properties of a specific node by its internal elementId or a known property."""
        # Using elementId in Neo4j 5+
        query = """
        MATCH (n {snapshot_id: $snapshot_id})
        WHERE elementId(n) = $node_id
        RETURN n
        """
        if not neo4j_driver.driver:
            neo4j_driver.connect()
        async with neo4j_driver.driver.session() as session:
            result = await session.run(query, snapshot_id=self.snapshot_id, node_id=node_id)
            record = await result.single()
            if not record:
                return {}
            return self._format_node(record["n"])

    async def expand_node(self, node_id: str) -> Dict[str, Any]:
        """Expands relationships 1 hop out from a specific node."""
        query = """
        MATCH (n {snapshot_id: $snapshot_id})
        WHERE elementId(n) = $node_id
        OPTIONAL MATCH (n)-[r]-(m {snapshot_id: $snapshot_id})
        RETURN n, r, m LIMIT 100
        """
        return await self._execute_and_format(query, {"node_id": node_id})

    async def _execute_and_format(self, query: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a query returning n, r, m and formats it for Cytoscape.js"""
        if params is None:
            params = {}
        params["snapshot_id"] = self.snapshot_id
        
        nodes = {}
        edges = []
        
        if not neo4j_driver.driver:
            neo4j_driver.connect()

        async with neo4j_driver.driver.session() as session:
            result = await session.run(query, **params)
            async for record in result:
                # Add source node
                n = record.get("n")
                if n:
                    formatted_n = self._format_node(n)
                    nodes[formatted_n["data"]["id"]] = formatted_n
                
                # Add target node if exists
                m = record.get("m")
                if m:
                    formatted_m = self._format_node(m)
                    nodes[formatted_m["data"]["id"]] = formatted_m
                    
                # Add edge if exists
                r = record.get("r")
                # IMPORTANT: neo4j-python-driver v5 Relationship.__bool__ returns False
                # when the relationship has no properties (empty dict). Must use `is not None`.
                if r is not None and n is not None and m is not None:
                    # Neo4j Python driver v5+: start_node and end_node are Node objects
                    # with an element_id attribute.
                    try:
                        start_id = r.start_node.element_id
                        end_id = r.end_node.element_id
                    except AttributeError:
                        # Older driver or unusual result shape — fall back to nodes list
                        try:
                            start_id = r.nodes[0].element_id
                            end_id = r.nodes[1].element_id
                        except Exception:
                            start_id = None
                            end_id = None

                    if start_id and end_id:
                        edges.append({
                            "data": {
                                "id": r.element_id,
                                "source": start_id,
                                "target": end_id,
                                "label": r.type,
                                "resolution": dict(r.items()).get("resolution", "exact")
                            }
                        })
                    
        return {
            "nodes": list(nodes.values()),
            "edges": edges
        }

    def _format_node(self, node) -> Dict[str, Any]:
        """Formats a Neo4j node into a Cytoscape.js node object."""
        labels = list(node.labels)
        primary_label = labels[0] if labels else "Unknown"
        
        props = dict(node.items())
        
        # Display name logic
        display_name = props.get("name") or props.get("path") or props.get("qualified_name") or "Unnamed"
        
        return {
            "data": {
                "label": display_name,
                "type": primary_label,
                **props,
                # element_id MUST come after **props — Repository nodes have an "id" property
                # (the repo UUID) which would otherwise overwrite the Neo4j element_id,
                # causing Cytoscape edge source/target mismatches.
                "id": node.element_id,
            }
        }
