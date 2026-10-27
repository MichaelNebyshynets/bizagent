"""Хранилище состояния агента в PostgreSQL (DB_BACKEND=postgres). Интерфейс тот же, что у Store (store.py).

Таблицы из schema.sql: agent_conversations, agent_messages, agent_pending_actions, agent_tool_calls.
Недостающие колонки (title, updated_at, kind) добавляются автоматически при первом обращении:
см. MIGRATION_SQL. Сообщения хранятся как JSON в agent_messages.content:
    kind='model'   — сообщение для модели (с tool_calls, tool_call_id и т.д.)
    kind='display' — сообщение, которое видит пользователь в чате

Подключения берутся из пула (не открываем новое соединение на каждый запрос).
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Iterator

import psycopg2
from psycopg2.extras import Json
from psycopg2.pool import ThreadedConnectionPool

from ..clock import Clock
from ..context import Principal
from ..errors import NotFound
from .store import AuditRecord, Conversation, PendingAction

log = logging.getLogger("agent.store")

MIGRATION_SQL = """
ALTER TABLE agent_conversations ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_conversations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS kind VARCHAR(10) NOT NULL DEFAULT 'model';
CREATE INDEX IF NOT EXISTS idx_agent_conversations_owner ON agent_conversations (company_id, user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_messages_conversation ON agent_messages (conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_company ON agent_tool_calls (company_id, id DESC);
"""

_CONV_COLS = "id, user_id, company_id, title, created_at, updated_at"
_PENDING_COLS = "id, conversation_id, user_id, company_id, tool_name, args, summary, created_at, expires_at, status"


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


class PostgresStore:
    def __init__(self, dsn: str, clock: Clock, confirm_ttl_min: int = 15, max_connections: int = 10) -> None:
        self.dsn = dsn
        self._clock = clock
        self._ttl = timedelta(minutes=confirm_ttl_min)
        self._max = max_connections
        self._pool: ThreadedConnectionPool | None = None
        self._lock = threading.Lock()

    # ---- подключение. Ленивое: импорт приложения и тесты не требуют запущенного Postgres
    def _ensure_pool(self) -> ThreadedConnectionPool:
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    pool = ThreadedConnectionPool(1, self._max, self.dsn)
                    conn = pool.getconn()
                    try:
                        with conn, conn.cursor() as cur:
                            cur.execute(MIGRATION_SQL)
                    except psycopg2.errors.UndefinedTable as e:
                        pool.putconn(conn)
                        pool.closeall()
                        raise RuntimeError("Таблицы агента не найдены: сначала примените schema.sql к базе.") from e
                    pool.putconn(conn)
                    self._pool = pool
        return self._pool

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        pool = self._ensure_pool()
        conn = pool.getconn()
        try:
            with conn:  # commit при успехе, rollback при исключении
                with conn.cursor() as cur:
                    yield cur
        finally:
            pool.putconn(conn)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None

    # ---- диалоги
    @staticmethod
    def _conv(row) -> Conversation:
        cid, uid, comp, title, created, updated = row
        return Conversation(cid, uid, comp, title=title, created_at=created, updated_at=updated)

    def get_or_create_conversation(self, p: Principal, conversation_id: str | None) -> Conversation:
        if conversation_id is not None:
            return self.get_conversation(p, conversation_id)
        now = self._clock()
        conv = Conversation(uuid.uuid4().hex, p.user_id, p.company_id, created_at=now, updated_at=now)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO agent_conversations (id, user_id, company_id, title, created_at, updated_at) VALUES (%s, %s, %s, '', %s, %s)",
                (conv.id, p.user_id, p.company_id, now, now),
            )
        return conv

    def get_conversation(self, p: Principal, conversation_id: str) -> Conversation:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT {_CONV_COLS} FROM agent_conversations WHERE id = %s AND user_id = %s AND company_id = %s",
                (conversation_id, p.user_id, p.company_id),
            )
            row = cur.fetchone()
            if row is None:
                raise NotFound("Диалог не найден.")
            conv = self._conv(row)
            cur.execute("SELECT kind, content FROM agent_messages WHERE conversation_id = %s ORDER BY id", (conv.id,))
            for kind, content in cur.fetchall():
                (conv.display if kind == "display" else conv.messages).append(json.loads(content))
        conv.saved_messages, conv.saved_display = len(conv.messages), len(conv.display)
        return conv

    def list_conversations(self, p: Principal, limit: int = 50) -> list[Conversation]:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT {_CONV_COLS} FROM agent_conversations WHERE user_id = %s AND company_id = %s ORDER BY updated_at DESC, created_at DESC LIMIT %s",
                (p.user_id, p.company_id, limit),
            )
            return [self._conv(r) for r in cur.fetchall()]

    def delete_conversation(self, p: Principal, conversation_id: str) -> None:
        with self._cursor() as cur:
            # сообщения и действия удалятся каскадом (ON DELETE CASCADE в schema.sql), аудит останется
            cur.execute(
                "DELETE FROM agent_conversations WHERE id = %s AND user_id = %s AND company_id = %s",
                (conversation_id, p.user_id, p.company_id),
            )
            if cur.rowcount == 0:
                raise NotFound("Диалог не найден.")

    def _insert_messages(self, cur, conversation_id: str, kind: str, msgs: list[dict[str, Any]]) -> None:
        if msgs:
            cur.executemany(
                "INSERT INTO agent_messages (conversation_id, role, content, kind) VALUES (%s, %s, %s, %s)",
                [(conversation_id, m.get("role", "user"), _dumps(m), kind) for m in msgs],
            )

    def save_conversation(self, conv: Conversation) -> None:
        """Дописывает в БД новые сообщения этого хода (старые не трогаем) и обновляет заголовок и время."""
        conv.updated_at = self._clock()
        with self._cursor() as cur:
            self._insert_messages(cur, conv.id, "model", conv.messages[conv.saved_messages:])
            self._insert_messages(cur, conv.id, "display", conv.display[conv.saved_display:])
            cur.execute("UPDATE agent_conversations SET title = %s, updated_at = %s WHERE id = %s", (conv.title, conv.updated_at, conv.id))
        conv.saved_messages, conv.saved_display = len(conv.messages), len(conv.display)

    def add_system_note(self, conversation_id: str, text: str, display: dict[str, Any] | None = None) -> None:
        with self._cursor() as cur:
            self._insert_messages(cur, conversation_id, "model", [{"role": "user", "content": f"[Системное уведомление] {text}"}])
            self._insert_messages(cur, conversation_id, "display", [display] if display else [])
            cur.execute("UPDATE agent_conversations SET updated_at = %s WHERE id = %s", (self._clock(), conversation_id))

    # ---- действия, ожидающие подтверждения
    @staticmethod
    def _pending(row) -> PendingAction:
        aid, cid, uid, comp, tool, args, summary, created, expires, status = row
        return PendingAction(aid, cid, uid, comp, tool, args, summary, created, expires, status)

    def create_pending(self, p: Principal, conversation_id: str, tool_name: str, args: dict[str, Any], summary: str) -> PendingAction:
        now = self._clock()
        act = PendingAction(uuid.uuid4().hex, conversation_id, p.user_id, p.company_id, tool_name, args, summary, now, now + self._ttl)
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO agent_pending_actions ({_PENDING_COLS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (act.id, act.conversation_id, act.user_id, act.company_id, act.tool_name, Json(act.args), act.summary, act.created_at, act.expires_at, act.status),
            )
        return act

    def get_pending(self, p: Principal, action_id: str) -> PendingAction:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT {_PENDING_COLS} FROM agent_pending_actions WHERE id = %s AND user_id = %s AND company_id = %s",
                (action_id, p.user_id, p.company_id),
            )
            row = cur.fetchone()
        if row is None:
            raise NotFound("Действие не найдено.")
        return self._pending(row)

    def pending_for(self, p: Principal, action_ids: list[str]) -> dict[str, PendingAction]:
        if not action_ids:
            return {}
        with self._cursor() as cur:
            cur.execute(
                f"SELECT {_PENDING_COLS} FROM agent_pending_actions WHERE id = ANY(%s) AND user_id = %s AND company_id = %s",
                (list(action_ids), p.user_id, p.company_id),
            )
            return {r[0]: self._pending(r) for r in cur.fetchall()}

    def claim_pending(self, act: PendingAction, new_status: str) -> bool:
        # Атомарно: из двух одновременных «Подтвердить» строку обновит только один запрос
        with self._cursor() as cur:
            cur.execute(
                "UPDATE agent_pending_actions SET status = %s WHERE id = %s AND status = 'pending' RETURNING id",
                (new_status, act.id),
            )
            ok = cur.fetchone() is not None
        if ok:
            act.status = new_status
        return ok

    def set_pending_status(self, act: PendingAction, status: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE agent_pending_actions SET status = %s WHERE id = %s", (status, act.id))
        act.status = status

    # ---- аудит
    def log(self, p: Principal, conversation_id: str | None, tool: str, args: dict[str, Any], status: str, detail: str = "") -> None:
        try:
            with self._cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_tool_calls (user_id, company_id, conversation_id, role, tool_name, args, status, detail, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (p.user_id, p.company_id, conversation_id, p.role, tool, Json(args or {}), status, (detail or "")[:300], self._clock()),
                )
        except psycopg2.Error:  # сбой записи аудита не должен ломать ответ пользователю
            log.exception("не удалось записать аудит: %s %s", tool, status)

    def audit_for_company(self, company_id: int, limit: int = 50) -> list[AuditRecord]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT created_at, user_id, company_id, role, conversation_id, tool_name, args, status, COALESCE(detail, '') "
                "FROM agent_tool_calls WHERE company_id = %s ORDER BY id DESC LIMIT %s",
                (company_id, limit),
            )
            return [AuditRecord(*r) for r in cur.fetchall()]
