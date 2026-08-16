import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from archon.pipeline.analysis.analyzer import StaticAnalyzer

@pytest.mark.asyncio
async def test_static_analyzer_queries():
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    
    analyzer = StaticAnalyzer(repo_id, snapshot_id)
    
    mock_session = AsyncMock()
    # Provide fake result data for the Neo4j queries
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"qname": "main.func", "fan_out": 2, "cc": 5, "fan_in": 1, "incoming_coupling": 3, "outgoing_coupling": 2, "cycle_count": 3}]
    mock_session.run.return_value = mock_result
    
    with patch("archon.pipeline.analysis.analyzer.neo4j_driver") as mock_driver:
        with patch("archon.pipeline.analysis.analyzer.async_session_factory") as mock_db_factory:
            mock_driver.driver.session.return_value.__aenter__.return_value = mock_session
            
            mock_db = AsyncMock()
            mock_db.add_all = MagicMock()
            mock_db_factory.return_value.__aenter__.return_value = mock_db
            
            await analyzer.run_analysis()
            
            # Verify Neo4j was queried for metrics
            assert mock_session.run.call_count >= 5
            
            # Verify metrics were persisted to Postgres
            assert mock_db.add_all.call_count == 1
            added_metrics = mock_db.add_all.call_args[0][0]
            
            # Verify metric labels and sources
            assert len(added_metrics) > 0
            for metric in added_metrics:
                assert metric.snapshot_id == str(snapshot_id)
                # StaticAnalyzer emits "deterministic" metrics, risk heuristic emits "archon_heuristic_v1"
                assert metric.metric_source == "deterministic"
