"""Хранилище состояния агента: диалоги, действия на подтверждении, журнал аудита.

Две реализации с одинаковым интерфейсом:
  • Store (этот файл) — в памяти. Режим DB_BACKEND=mock и тесты. Всё пропадает при перезапуске.
  • PostgresStore (pg_store.py) — таблицы agent_conversations, agent_messages, agent_pending_actions,
    agent_tool_calls. Режим DB_BACKEND=postgres. История переживает перезапуск.

В диалоге два списка сообщений:
  • messages — то, что видит МОДЕЛЬ (с вызовами инструментов, служебными уведомлениями, пометками о файлах);
  • display — то, что видит ПОЛЬЗОВАТЕЛЬ в чате (вопрос, ответ, какие инструменты вызваны, карточки подтверждения).
Так фронтенд показывает историю «как было», а модель получает полный технический контекст.

Изоляция: каждый метод, который принимает Principal, видит только диалоги и действия этого пользователя
в его компании. Чужой диалог выглядит как несуществующий (NotFound), а не «запрещён».
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..clock import Clock
from ..context import Principal
from ..errors import NotFound

TITLE_MAX = 60


def make_title(text: str) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= TITLE_MAX else line[: TITLE_MAX - 1].rstrip() + "…"


@dataclass
class Conversation:
    id: str
    user_id: int
    company_id: int
    messages: list[dict[str, Any]] = field(default_factory=list)  # для модели
    display: list[dict[str, Any]] = field(default_factory=list)  # для пользователя
    title: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # сколько сообщений уже сохранено в БД (PostgresStore дописывает только новые)
    saved_messages: int = field(default=0, repr=False)
    saved_display: int = field(default=0, repr=False)

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title or "Новый чат",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class PendingAction:
    id: str
    conversation_id: str
    user_id: int
    company_id: int
    tool_name: str
    args: dict[str, Any]  # уже провалидированные аргументы (JSON-совместимые)
    summary: str
    created_at: datetime
    expires_at: datetime
    status: str = "pending"  # pending | confirmed | rejected | expired | failed


@dataclass
class AuditRecord:
    ts: datetime
    user_id: int
    company_id: int
    role: str
    conversation_id: str | None
    tool: str
    args: dict[str, Any]
    status: str  # ok | error | denied | pending | confirmed | rejected | expired | failed
    detail: str = ""


class Store:
    """Хранилище в памяти (DB_BACKEND=mock, тесты)."""

    def __init__(self, clock: Clock, confirm_ttl_min: int = 15) -> None:
        self._clock = clock
        self._ttl = timedelta(minutes=confirm_ttl_min)
        self._conversations: dict[str, Conversation] = {}
        self._pending: dict[str, PendingAction] = {}
        self.audit_log: list[AuditRecord] = []

    # ---- диалоги
    def get_or_create_conversation(self, p: Principal, conversation_id: str | None) -> Conversation:
        if conversation_id is None:
            now = self._clock()
            conv = Conversation(uuid.uuid4().hex, p.user_id, p.company_id, created_at=now, updated_at=now)
            self._conversations[conv.id] = conv
            return conv
        return self.get_conversation(p, conversation_id)

    def get_conversation(self, p: Principal, conversation_id: str) -> Conversation:
        conv = self._conversations.get(conversation_id)
        if conv is None or conv.user_id != p.user_id or conv.company_id != p.company_id:
            raise NotFound("Диалог не найден.")
        return conv

    def list_conversations(self, p: Principal, limit: int = 50) -> list[Conversation]:
        mine = [c for c in self._conversations.values() if c.user_id == p.user_id and c.company_id == p.company_id]
        return sorted(mine, key=lambda c: c.updated_at, reverse=True)[:limit]

    def delete_conversation(self, p: Principal, conversation_id: str) -> None:
        conv = self.get_conversation(p, conversation_id)  # NotFound, если чужой
        del self._conversations[conv.id]
        for aid in [a.id for a in self._pending.values() if a.conversation_id == conv.id]:
            del self._pending[aid]

    def save_conversation(self, conv: Conversation) -> None:
        """Конец хода агента. В памяти сохранять нечего, только отметить время."""
        conv.updated_at = self._clock()
        conv.saved_messages, conv.saved_display = len(conv.messages), len(conv.display)

    def add_system_note(self, conversation_id: str, text: str, display: dict[str, Any] | None = None) -> None:
        """Служебное сообщение для модели (например, «пользователь подтвердил действие») и, если задано, строка в чате."""
        conv = self._conversations.get(conversation_id)
        if conv is not None:
            conv.messages.append({"role": "user", "content": f"[Системное уведомление] {text}"})
            if display:
                conv.display.append(display)
            self.save_conversation(conv)

    # ---- действия, ожидающие подтверждения
    def create_pending(self, p: Principal, conversation_id: str, tool_name: str, args: dict[str, Any], summary: str) -> PendingAction:
        now = self._clock()
        act = PendingAction(uuid.uuid4().hex, conversation_id, p.user_id, p.company_id, tool_name, args, summary, now, now + self._ttl)
        self._pending[act.id] = act
        return act

    def get_pending(self, p: Principal, action_id: str) -> PendingAction:
        act = self._pending.get(action_id)
        # Подтвердить может только тот, чьё это действие, и в его компании
        if act is None or act.user_id != p.user_id or act.company_id != p.company_id:
            raise NotFound("Действие не найдено.")
        return act

    def pending_for(self, p: Principal, action_ids: list[str]) -> dict[str, PendingAction]:
        out = {}
        for aid in action_ids:
            act = self._pending.get(aid)
            if act and act.user_id == p.user_id and act.company_id == p.company_id:
                out[aid] = act
        return out

    def claim_pending(self, act: PendingAction, new_status: str) -> bool:
        """Атомарно перевести действие из pending в new_status. False — его уже кто-то обработал
        (двойной клик, повторный запрос). Так одно действие не выполнится дважды."""
        current = self._pending.get(act.id)
        if current is None or current.status != "pending":
            return False
        current.status = act.status = new_status
        return True

    def set_pending_status(self, act: PendingAction, status: str) -> None:
        act.status = status
        if act.id in self._pending:
            self._pending[act.id].status = status

    # ---- аудит: кто, когда, какой инструмент, с какими аргументами и чем кончилось
    def log(self, p: Principal, conversation_id: str | None, tool: str, args: dict[str, Any], status: str, detail: str = "") -> None:
        self.audit_log.append(AuditRecord(self._clock(), p.user_id, p.company_id, p.role, conversation_id, tool, args, status, detail[:300]))

    def audit_for_company(self, company_id: int, limit: int = 50) -> list[AuditRecord]:
        rows = [r for r in self.audit_log if r.company_id == company_id]
        return list(reversed(rows))[:limit]  # новые сверху
