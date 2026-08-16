import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from archon.pipeline.graph.builder import GraphBuilder
from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction, ResolvedCall

@pytest.mark.asyncio
async def test_graph_builder_queries():
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    
    # Mock Parsed Data
    parsed_file = ParsedFile(
        path="main.py",
        language="python",
        total_lines=10,
        docstring="Module doc",
        classes=[],
        functions=[
            ParsedFunction(
                name="main",
                qualified_name="main.main",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=False,
                cyclomatic_complexity=1,
                line_count=5,
                end_line=5,
                nesting_depth=0,
                docstring="Main func",
                calls=[ResolvedCall(raw_name="print", target_qualified_name=None, resolution="inferred")]
            )
        ],
        imports=[]
    )
    
    builder = GraphBuilder(repo_id, snapshot_id, "abc1234")
    
    # Mock Neo4j session
    mock_session = AsyncMock()
    
    # Mock the driver and db
    with patch("archon.pipeline.graph.builder.neo4j_driver") as mock_driver, \
         patch("archon.pipeline.graph.builder.async_session_factory") as mock_db_factory:
         
        mock_driver.driver.session.return_value.__aenter__.return_value = mock_session
        
        mock_db = AsyncMock()
        # mock db.execute().scalars().all() for GitCommits and GitFileChanges
        mock_cursor = MagicMock()
        mock_cursor.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_cursor)
        mock_db_factory.return_value.__aenter__.return_value = mock_db
        
        await builder.build([parsed_file])
        
        # Verify queries were executed
        assert mock_session.run.call_count > 0
        
        # Check that Repo node was merged with snapshot
        repo_call = mock_session.run.call_args_list[0]
        assert "MERGE (r:Repository {id: $repo_id})" in repo_call[0][0]
        assert repo_call[1]["snapshot_id"] == str(snapshot_id)
        
        # Check File node merge
        file_call = mock_session.run.call_args_list[1]
        assert "MERGE (f:File {path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})" in file_call[0][0]
        
        # Check Function node merge
        func_call = [call for call in mock_session.run.call_args_list if "MERGE (func:Function" in call[0][0]][0]
        assert func_call[1]["docstring"] == "Main func"
        
        # Check Call resolution
        call_call = [call for call in mock_session.run.call_args_list if "MERGE (caller)-[:CALLS" in call[0][0]][0]
        assert call_call[1]["resolution"] == "inferred"
