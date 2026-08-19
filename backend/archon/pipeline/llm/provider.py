import abc
import json
from typing import AsyncGenerator, Dict, Any, List
import structlog
import httpx
from archon.config import settings
from archon.models.analyst import AnalystResponse

logger = structlog.get_logger(__name__)

class LLMProvider(abc.ABC):
    @abc.abstractmethod
    async def analyze(self, system_prompt: str, context: str, question: str) -> AnalystResponse:
        pass

    @abc.abstractmethod
    async def analyze_stream(self, system_prompt: str, context: str, question: str, tools: list = None) -> AsyncGenerator[str | dict, None]:
        pass


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str = None, model: str = None):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
        
    def _get_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    async def analyze(self, system_prompt: str, context: str, question: str) -> AnalystResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"<EVIDENCE>\n{context}\n</EVIDENCE>\n\n<QUESTION>\n{question}\n</QUESTION>"}
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "analyst_response",
                    "strict": True,
                    "schema": AnalystResponse.model_json_schema()
                }
            }
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self._get_url(),
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return AnalystResponse.model_validate_json(content)

    async def analyze_stream(self, system_prompt: str, context: str, question: str, tools: list = None) -> AsyncGenerator[str | dict, None]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"<EVIDENCE>\n{context}\n</EVIDENCE>\n\n<QUESTION>\n{question}\n</QUESTION>"}
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.1
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        else:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "analyst_response",
                    "strict": True,
                    "schema": AnalystResponse.model_json_schema()
                }
            }
            
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", self._get_url(), headers=self._get_headers(), json=payload) as response:
                    response.raise_for_status()
                    
                    tool_calls_buffer = {}
                    
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                            
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                            
                        try:
                            chunk = json.loads(data_str)
                            if not chunk.get("choices"):
                                continue
                                
                            delta = chunk["choices"][0].get("delta", {})
                            
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                                
                            if "tool_calls" in delta and delta["tool_calls"]:
                                for tc in delta["tool_calls"]:
                                    idx = tc.get("index", 0)
                                    if idx not in tool_calls_buffer:
                                        tool_calls_buffer[idx] = {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {
                                                "name": tc.get("function", {}).get("name", ""),
                                                "arguments": tc.get("function", {}).get("arguments", "")
                                            }
                                        }
                                    else:
                                        func = tc.get("function", {})
                                        if func.get("name"):
                                            tool_calls_buffer[idx]["function"]["name"] += func["name"]
                                        if func.get("arguments"):
                                            tool_calls_buffer[idx]["function"]["arguments"] += func["arguments"]
                        except json.JSONDecodeError:
                            continue

                    if tool_calls_buffer:
                        for idx in sorted(tool_calls_buffer.keys()):
                            yield {"tool_call": tool_calls_buffer[idx]}
                        
        except Exception as e:
            logger.error("llm_stream_error", error=str(e))
            yield {"error": f"LLM Provider Error: {str(e)}"}


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = None):
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not configured in environment.")
        resolved_model = model or (settings.LLM_MODEL if settings.LLM_MODEL and settings.LLM_MODEL not in ("llama3", "ollama") else None) or "meta-llama/llama-3.3-70b-instruct:free"
        super().__init__(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY.strip(),
            model=resolved_model
        )


class GeminiProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = None):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured in environment.")
        resolved_model = model or (settings.LLM_MODEL if settings.LLM_MODEL and settings.LLM_MODEL not in ("llama3", "ollama") else None) or "gemini-2.0-flash"
        super().__init__(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=settings.GEMINI_API_KEY.strip(),
            model=resolved_model
        )


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = None):
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured in environment.")
        resolved_model = model or (settings.LLM_MODEL if settings.LLM_MODEL and settings.LLM_MODEL not in ("llama3", "ollama") else None) or "llama3-70b-8192"
        super().__init__(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY.strip(),
            model=resolved_model
        )

class OllamaProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = None):
        super().__init__(
            base_url=f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1",
            api_key="ollama", # Some clients complain if API key is missing
            model=model or settings.LLM_MODEL or "llama3"
        )

def get_llm_provider(provider_name: str = None, model: str = None) -> LLMProvider:
    name = (provider_name or settings.LLM_PROVIDER or "groq").lower()
    
    if name == "openrouter" and settings.OPENROUTER_API_KEY:
        return OpenRouterProvider(model=model)
    elif name == "gemini" and settings.GEMINI_API_KEY:
        return GeminiProvider(model=model)
    elif name == "groq" and settings.GROQ_API_KEY:
        return GroqProvider(model=model)
    elif name == "ollama":
        return OllamaProvider(model=model)
    else:
        if settings.GROQ_API_KEY:
            return GroqProvider(model=model)
        elif settings.GEMINI_API_KEY:
            return GeminiProvider(model=model)
        elif settings.OPENROUTER_API_KEY:
            return OpenRouterProvider(model=model)
        else:
            return OllamaProvider(model=model)
