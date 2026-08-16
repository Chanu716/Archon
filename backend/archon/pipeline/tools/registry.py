import inspect
from typing import Any, Callable, Dict, List, Type
from pydantic import BaseModel
import structlog
from archon.models.tools import ToolResult

logger = structlog.get_logger(__name__)

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, input_model: Type[BaseModel]):
        def decorator(func: Callable):
            self._tools[name] = {
                "name": name,
                "description": description,
                "input_model": input_model,
                "handler": func
            }
            return func
        return decorator

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        tools = []
        for name, metadata in self._tools.items():
            schema = metadata["input_model"].model_json_schema()
            # Pydantic schemas might have $defs, which OpenAI structured outputs don't support well in function calling
            # but standard json schema is usually fine.
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": metadata["description"],
                    "parameters": {
                        "type": "object",
                        "properties": schema.get("properties", {}),
                        "required": schema.get("required", [])
                    }
                }
            })
        return tools

    async def execute(self, tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """
        Executes a registered tool.
        `context` is a dict containing things like repository_id, snapshot_id, db_session, etc.
        """
        if tool_name not in self._tools:
            logger.error("unknown_tool_requested", tool=tool_name)
            return ToolResult(
                success=False,
                tool_name=tool_name,
                data="",
                error=f"Unknown tool: {tool_name}"
            )
            
        metadata = self._tools[tool_name]
        handler = metadata["handler"]
        input_model = metadata["input_model"]
        
        try:
            # Validate input arguments against the pydantic schema
            validated_input = input_model(**arguments)
            
            # Execute handler
            # We inject the validated input and the context
            # A handler must accept (input: BaseModel, context: Dict)
            if inspect.iscoroutinefunction(handler):
                result = await handler(validated_input, context)
            else:
                result = handler(validated_input, context)
                
            # If the handler returned a ToolResult, use it. Otherwise wrap it.
            if isinstance(result, ToolResult):
                return result
                
            return ToolResult(
                success=True,
                tool_name=tool_name,
                data=result
            )
            
        except Exception as e:
            logger.error("tool_execution_failed", tool=tool_name, error=str(e))
            return ToolResult(
                success=False,
                tool_name=tool_name,
                data="",
                error=str(e)
            )

# Global registry
tool_registry = ToolRegistry()
