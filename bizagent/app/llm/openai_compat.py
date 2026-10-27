"""Провайдер для любого сервера с OpenAI-совместимым API (/chat/completions):
vLLM, Ollama (http://localhost:11434/v1), LM Studio, OpenRouter, облачные API и т.д.

ВАЖНО: не каждая модель умеет надёжно вызывать инструменты (tool calling).
При выборе открытой модели проверяй именно это, а не только качество чата.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from .base import LLMError, LLMResponse, ToolCall


class OpenAICompatLLM:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 60.0,
        temperature: float = 0.2,  # для работы с данными и инструментами нужна низкая «креативность»
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = await self._client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM недоступна или вернула неожиданный ответ: {e}") from e

        calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            calls.append(_parse_tool_call(tc.get("id"), fn.get("name", ""), fn.get("arguments")))
        return LLMResponse(content=msg.get("content"), tool_calls=calls)


def _parse_tool_call(call_id: str | None, name: str, raw: Any) -> ToolCall:
    call_id = call_id or f"call_{uuid.uuid4().hex[:12]}"  # некоторые серверы не присылают id
    # Аргументы обычно приходят JSON-строкой, но некоторые серверы отдают уже словарь
    if isinstance(raw, dict):
        return ToolCall(id=call_id, name=name, arguments=raw, raw_arguments=json.dumps(raw, ensure_ascii=False))
    raw_s = raw if isinstance(raw, str) else ""
    try:
        args = json.loads(raw_s) if raw_s.strip() else {}
        if not isinstance(args, dict):
            raise ValueError("ожидался JSON-объект")
    except ValueError as e:
        return ToolCall(id=call_id, name=name, arguments_error=f"невалидный JSON в аргументах: {e}", raw_arguments=raw_s)
    return ToolCall(id=call_id, name=name, arguments=args, raw_arguments=raw_s)
