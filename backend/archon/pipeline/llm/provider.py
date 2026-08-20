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
        payload = {"model": self.model, "messages": messages, "temperature": 0.1}
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(self._get_url(), headers=self._get_headers(), json=payload)
            if not response.is_success:
                raise ValueError(f"LLM API error {response.status_code}: {response.text[:400]}")
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return AnalystResponse.model_validate_json(content)

    async def _call_with_tools_once(self, messages: list, tools: list) -> dict:
        """Single non-streaming call that may return tool_calls or a direct answer."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "tools": tools,
            "tool_choice": "auto",
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(self._get_url(), headers=self._get_headers(), json=payload)
            if not response.is_success:
                raise ValueError(f"LLM API error {response.status_code}: {response.text[:400]}")
            return response.json()

    async def _stream_answer(self, messages: list) -> AsyncGenerator[str, None]:
        """Pure streaming call (no tools) for the final answer."""
        payload = {"model": self.model, "messages": messages, "stream": True, "temperature": 0.1}
        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream("POST", self._get_url(), headers=self._get_headers(), json=payload) as response:
                if not response.is_success:
                    body = await response.aread()
                    raise ValueError(f"LLM stream error {response.status_code}: {body[:400].decode(errors='replace')}")
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
                        if delta.get("content"):
                            yield delta["content"]
                    except json.JSONDecodeError:
                        continue

    async def analyze_stream(
        self,
        system_prompt: str,
        context: str,
        question: str,
        tools: list = None,
    ) -> AsyncGenerator[str | dict, None]:
        """
        Gather-then-stream pattern:
        - With tools: one non-streaming round to get tool_calls, yield them for execution.
          Caller updates context with evidence and calls again. When LLM answers directly, stream it.
        - Without tools: pure streaming answer.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"<EVIDENCE>\n{context}\n</EVIDENCE>\n\n<QUESTION>\n{question}\n</QUESTION>"}
        ]

        if tools:
            try:
                data = await self._call_with_tools_once(messages, tools)
            except Exception as e:
                logger.error("tool_call_failed", error=str(e))
                yield {"error": f"LLM Provider Error: {str(e)}"}
                return

            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason", "stop")
            message = choice.get("message", {})

            if finish_reason == "tool_calls" or message.get("tool_calls"):
                for tc in (message.get("tool_calls") or []):
                    yield {"tool_call": tc}
                return  # Caller loops with updated context

            # LLM answered directly without calling tools
            final_content = message.get("content") or ""
            if final_content:
                for i in range(0, len(final_content), 80):
                    yield final_content[i:i + 80]
            return

        # No tools requested — stream directly
        try:
            async for token in self._stream_answer(messages):
                yield token
        except Exception as e:
            logger.error("llm_stream_error", error=str(e))
            yield {"error": f"LLM Provider Error: {str(e)}"}


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = None):
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not configured.")
        super().__init__(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY.strip(),
            model=model or "meta-llama/llama-3.3-70b-instruct"
        )


class GeminiProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = None):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        super().__init__(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=settings.GEMINI_API_KEY.strip(),
            model=model or "gemini-3.6-flash"
        )


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = None):
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured.")
        super().__init__(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY.strip(),
            model=model or "llama-3.3-70b-versatile"
        )


def get_llm_provider(provider_name: str = None, model: str = None) -> LLMProvider:
    name = (provider_name or settings.LLM_PROVIDER or "gemini").lower()
    if name == "openrouter" and settings.OPENROUTER_API_KEY:
        return OpenRouterProvider(model=model)
    elif name == "gemini" and settings.GEMINI_API_KEY:
        return GeminiProvider(model=model)
    elif name == "groq" and settings.GROQ_API_KEY:
        return GroqProvider(model=model)
    else:
        if settings.GEMINI_API_KEY:
            return GeminiProvider(model=model)
        elif settings.OPENROUTER_API_KEY:
            return OpenRouterProvider(model=model)
        elif settings.GROQ_API_KEY:
            return GroqProvider(model=model)
        else:
            raise ValueError("No LLM API key configured (GEMINI_API_KEY, OPENROUTER_API_KEY, or GROQ_API_KEY).")
