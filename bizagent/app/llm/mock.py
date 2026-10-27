"""Две «ненастоящие» модели. Обе нужны, пока нет доступа к настоящей.

ScriptedLLM — для тестов: отдаёт заранее заданные ответы по очереди. Так мы проверяем ЦИКЛ АГЕНТА
(права, подтверждения, изоляцию), не завися от того, что скажет настоящая модель.

MockLLM — демо-заглушка БЕЗ ИИ: по ключевым словам выбирает инструмент. Нужна, чтобы
фронтендер мог пользоваться чатом уже сегодня. Это не интеллект, на защите так и говорим.
"""
from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Any, Callable

from ..clock import Clock
from .base import LLMError, LLMResponse, ToolCall


def call(tool: str, /, **args: Any) -> LLMResponse:
    """Ответ модели: «вызови инструмент». tool — позиционный, чтобы можно было передать аргумент name=..."""
    return LLMResponse(tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=tool, arguments=args)])


def say(text: str) -> LLMResponse:
    """Ответ модели: обычный текст (конец цикла)."""
    return LLMResponse(content=text)


class ScriptedLLM:
    def __init__(self, script: list[LLMResponse | Callable[[list[dict]], LLMResponse]]):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []  # что именно получала «модель», для проверок в тестах

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self.script:
            raise LLMError("ScriptedLLM: сценарий закончился")
        item = self.script.pop(0)
        return item(messages) if callable(item) else item


def _has(words: list[str], *stems: str) -> bool:
    return any(w.startswith(s) for w in words for s in stems)


class MockLLM:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        last = messages[-1]
        if last["role"] == "tool":
            return say("Результат инструмента (демо-режим, без ИИ):\n" + last["content"])

        text = last.get("content") or ""
        words = re.findall(r"[\w-]+", text.lower())
        today = self._clock().date()
        d_to, d_from = today.isoformat(), (today - timedelta(days=30)).isoformat()

        m = re.search(r"file_id=([0-9a-f]{32})", text)
        if m:  # пользователь приложил файл: в демо-режиме просто читаем его начало
            return call("read_uploaded_file", file_id=m.group(1))
        if _has(words, "файл", "документ", "загруж"):
            return call("list_uploaded_files")
        if _has(words, "созда", "добав") and _has(words, "клиент"):
            m = re.search(r"клиента\s+(.+)$", text, re.I)
            if not m:
                return say("Укажите имя клиента: «создай клиента Иван Петров».")
            return call("create_client", name=m.group(1).strip(" «»\""))
        if _has(words, "найд", "покаж") and _has(words, "клиент"):
            m = re.search(r"клиента\s+(.+)$", text, re.I)
            return call("find_client", query=(m.group(1) if m else text).strip(" «»\""))
        if _has(words, "залежал", "неликвид"):
            return call("list_slow_movers", days=90)
        if _has(words, "заканчива", "остатк", "склад"):
            return call("list_low_stock", threshold=5)
        if _has(words, "топ", "лучш", "популярн"):
            return call("get_top_products", date_from=d_from, date_to=d_to, limit=5, metric="revenue")
        if _has(words, "прибыл", "расход"):
            return call("get_profit_summary", date_from=d_from, date_to=d_to)
        if _has(words, "выруч", "продаж", "продал"):
            return call("get_sales_summary", date_from=d_from, date_to=d_to, group_by="none")
        if _has(words, "налог", "ндс", "усн", "эсчф", "закон", "регистрац"):
            return call("search_knowledge_base", query=text)
        return say(
            "Демо-режим без ИИ: я понимаю только ключевые слова "
            "(выручка, топ товаров, что заканчивается, что залежалось, прибыль, найди клиента …, "
            "создай клиента …, налоги). Подключите настоящую модель через LLM_PROVIDER=openai_compat."
        )
