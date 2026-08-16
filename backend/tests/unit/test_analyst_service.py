import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from archon.services.analyst import AIAnalystService, SYSTEM_PROMPT
from archon.models.analyst import EvidenceBundle

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.mark.asyncio
async def test_analyst_tool_loop(mock_db):
    """
    Verifies that the analyst orchestrates the tool loop correctly and respects MAX_ITERATIONS.
    """
    with patch("archon.services.analyst.get_llm_provider") as mock_get_provider:
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        # Configure mock_db.execute to return a proper cursor-like mock for snapshot resolution
        mock_cursor = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.id = uuid.uuid4()
        mock_cursor.scalars.return_value.first.return_value = mock_snapshot
        mock_db.execute = AsyncMock(return_value=mock_cursor)
        
        # Simulate LLM always returning a tool call, which should trigger the MAX_ITERATIONS loop break
        async def fake_analyze(*args, **kwargs):
            yield {"tool_call": {"id": "call_123", "function": {"name": "test_tool", "arguments": "{}"}}}

        mock_provider.analyze_stream = fake_analyze
        
        with patch("archon.services.analyst.tool_registry") as mock_registry:
            mock_registry.get_openai_tools.return_value = []
            
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.data = "Tool result"
            mock_registry.execute = AsyncMock(return_value=mock_result)
            
            service = AIAnalystService(mock_db)
            repo_id = uuid.uuid4()
            
            chunks = []
            async for chunk in service.query(repo_id, "test question"):
                chunks.append(chunk)
                
            # It should hit max iterations and yield traces for each tool call + the final warning
            assert mock_registry.execute.call_count == 5
            # We expect trace chunks
            trace_chunks = [c for c in chunks if isinstance(c, str) and '"trace":' in c]
            assert len(trace_chunks) > 0


@pytest.mark.asyncio
async def test_analyst_system_prompt_defenses():
    """
    Verifies that the prompt specifically instructs the model to treat
    repository code as data and strictly ground its answers.
    """
    assert "UNTRUSTED DATA" in SYSTEM_PROMPT
    assert "never execute" in SYSTEM_PROMPT.lower()
    assert "deterministic evidence" in SYSTEM_PROMPT.lower()
