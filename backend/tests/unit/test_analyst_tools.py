import pytest
import uuid
import json
from archon.pipeline.tools.registry import ToolRegistry
from pydantic import BaseModel
from archon.services.tools import handle_get_file

class DummyInput(BaseModel):
    dummy_val: str

@pytest.fixture
def mock_context():
    return {
        "db_session": None,
        "repository_id": str(uuid.uuid4()),
        "snapshot_id": str(uuid.uuid4())
    }

@pytest.mark.asyncio
async def test_tool_registry_registration_and_execution(mock_context):
    registry = ToolRegistry()
    
    @registry.register("test_tool", "A test tool", DummyInput)
    async def my_handler(input: DummyInput, context: dict):
        return f"Hello {input.dummy_val}"
        
    # Check schema generation
    schemas = registry.get_openai_tools()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "test_tool"
    assert "dummy_val" in schemas[0]["function"]["parameters"]["properties"]
    
    # Execute
    result = await registry.execute("test_tool", {"dummy_val": "world"}, mock_context)
    assert result.success
    assert result.tool_name == "test_tool"
    assert result.data == "Hello world"
    
@pytest.mark.asyncio
async def test_tool_registry_unknown_tool(mock_context):
    registry = ToolRegistry()
    result = await registry.execute("unknown", {}, mock_context)
    assert not result.success
    assert "Unknown tool" in result.error

from unittest.mock import patch

@pytest.mark.asyncio
async def test_get_file_handler_mocked(mock_context):
    with patch('archon.services.tools.RepositoryStorageService') as mock_storage:
        instance = mock_storage.return_value
        instance.get_file.return_value = "file content here"
        
        from archon.models.tools import GetFileInput
        input_data = GetFileInput(relative_path="src/main.py")
        
        result = await handle_get_file(input_data, mock_context)
        assert result.success
        assert result.data["path"] == "src/main.py"
        assert result.data["content"] == "file content here"

@pytest.mark.asyncio
async def test_get_file_handler_truncation(mock_context):
    with patch('archon.services.tools.RepositoryStorageService') as mock_storage:
        instance = mock_storage.return_value
        instance.get_file.return_value = "A" * 5000
        
        from archon.models.tools import GetFileInput
        input_data = GetFileInput(relative_path="src/big.py")
        
        result = await handle_get_file(input_data, mock_context)
        assert result.success
        assert result.truncated is True
        assert len(result.data["content"]) == 3000
