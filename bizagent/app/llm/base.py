"""Единый интерфейс к любой модели.

Остальной код (цикл агента) знает только про LLMProvider. Хочешь сменить модель, облако на
локальную vLLM/Ollama, пишешь новый провайдер, ядро не меняется.

Формат сообщений — как в OpenAI Chat Completions: это де-факто стандарт, его понимают
vLLM, Ollama, LM Studio, OpenRouter и т.д.:
  {"role": "system"|"user"|"assistant"|"tool", "content": str,
   "tool_calls": [...]       # только у assistant
   "tool_call_id": str}      # только у tool
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(Exception):
    """Модель недоступна или вернула неожиданный ответ."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    # Если модель прислала невалидный JSON в аргументах: тут причина, а сырая строка в raw_arguments.
    # Мы не падаем, а возвращаем ошибку модели, и она обычно исправляет вызов.
    arguments_error: str | None = None
    raw_arguments: str | None = None


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse: ...
