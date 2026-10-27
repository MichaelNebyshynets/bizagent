from __future__ import annotations

from ..clock import Clock
from ..config import Settings
from .base import LLMError, LLMProvider, LLMResponse, ToolCall

__all__ = ["LLMError", "LLMProvider", "LLMResponse", "ToolCall", "build_llm"]


def build_llm(settings: Settings, clock: Clock) -> LLMProvider:
    """Единственное место, где выбирается конкретная модель (по конфигу)."""
    if settings.llm_provider == "mock":
        from .mock import MockLLM

        return MockLLM(clock)
    if settings.llm_provider == "openai_compat":
        if not settings.llm_model:
            raise RuntimeError("Для LLM_PROVIDER=openai_compat задайте LLM_MODEL")
        from .openai_compat import OpenAICompatLLM  # импорт здесь: для mock-режима httpx не нужен

        return OpenAICompatLLM(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout_s=settings.llm_timeout_s,
        )
    raise RuntimeError(f"Неизвестный LLM_PROVIDER: {settings.llm_provider!r}")
