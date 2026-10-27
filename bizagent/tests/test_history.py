"""История чатов: список, заголовки, изоляция пользователей, карточки подтверждения, удаление,
переживание перезапуска. Один набор тестов для двух хранилищ:
  • Store (память) — всегда;
  • PostgresStore — только если задан BIZAGENT_TEST_PG, например
        BIZAGENT_TEST_PG="dbname=bizagent_test user=postgres password=postgres host=localhost" pytest tests/test_history.py
    ВНИМАНИЕ: тест пересоздаёт схему public в этой базе. Не указывайте рабочую базу!
"""
import dataclasses
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app.agent.actions import confirm_action, reject_action
from app.agent.loop import conversation_view, run_agent_events
from app.agent.store import Store
from app.bootstrap import build_runtime
from app.clock import MINSK
from app.config import Settings
from app.context import Principal
from app.errors import Conflict, Gone, NotFound
from app.kb import InMemoryKnowledgeBase
from app.llm.mock import ScriptedLLM, call, say
from app.mock_data import MockDB, seed

OWNER = Principal(1, 1, "owner")
MANAGER = Principal(2, 1, "manager")  # та же компания, другой пользователь
FLORA = Principal(4, 2, "owner")  # другая компания

PG_DSN = os.getenv("BIZAGENT_TEST_PG")
SCHEMA = Path(os.getenv("BIZAGENT_TEST_SCHEMA", Path(__file__).resolve().parents[2] / "schema.sql"))


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 27, 12, 0, tzinfo=MINSK)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def reset_pg(dsn: str) -> None:
    """Чистая схема: компании, пользователи и таблицы агента из schema.sql (без pgvector)."""
    import psycopg2

    wanted = re.compile(r"CREATE TABLE IF NOT EXISTS (companies|users|agent_\w+)\b")
    statements = [s.strip() for s in SCHEMA.read_text(encoding="utf-8").split(";") if wanted.search(s)]
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        for s in statements:
            cur.execute(s)
        cur.execute("INSERT INTO companies (id, name, unp) VALUES (1, 'Уютный дом (демо)', '000000001'), (2, 'Флора (демо)', '000000002')")
        cur.execute(
            "INSERT INTO users (id, company_id, email, role, name) VALUES "
            "(1, 1, 'owner@uyut.by', 'owner', 'В'), (2, 1, 'manager@uyut.by', 'manager', 'М'), "
            "(3, 1, 'accountant@uyut.by', 'accountant', 'Б'), (4, 2, 'owner@flora.by', 'owner', 'Ф')"
        )
    conn.close()


class HistoryContract:
    """Тесты, которые обязано проходить любое хранилище."""

    backend = "mock"

    def setUp(self):
        self.clock = FakeClock()
        self.tmp = tempfile.mkdtemp(prefix="bizagent-hist-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = MockDB()
        seed(self.db, self.clock().date())
        self.rt = self.runtime([])

    def runtime(self, script):
        self.llm = ScriptedLLM(script)
        settings = Settings(db_backend=self.backend, database_url=PG_DSN or "", upload_dir=self.tmp)
        rt = build_runtime(settings=settings, llm=self.llm, db=self.db, kb=InMemoryKnowledgeBase(), clock=self.clock)
        if hasattr(rt.store, "close"):
            self.addCleanup(rt.store.close)
        return rt

    async def chat(self, p, text, conv=None, script=None):
        if script is not None:
            self.llm.script = list(script)
        return [e async for e in run_agent_events(self.rt, p, conv, text)]

    async def test_new_chat_is_listed_with_title_newest_first(self):
        first = (await self.chat(OWNER, "Сколько продали в сентябре?", script=[say("1000 BYN")]))[-1]["conversation_id"]
        self.clock.advance(minutes=1)
        await self.chat(OWNER, "А в августе?", conv=first, script=[say("900 BYN")])
        self.clock.advance(minutes=1)
        second = (await self.chat(OWNER, "  Какие товары\\nзаканчиваются?  " * 5, script=[say("Сковорода")]))[-1]["conversation_id"]
        chats = [c.info() for c in self.rt.store.list_conversations(OWNER)]
        self.assertEqual([c["id"] for c in chats], [second, first])
        self.assertEqual(chats[1]["title"], "Сколько продали в сентябре?", "заголовок по первому вопросу, не меняется")
        self.assertLessEqual(len(chats[0]["title"]), 60)

    async def test_other_users_cannot_see_list_open_or_delete(self):
        conv = (await self.chat(OWNER, "секретный вопрос", script=[say("ответ")]))[-1]["conversation_id"]
        for other in (MANAGER, FLORA):
            self.assertEqual(self.rt.store.list_conversations(other), [])
            with self.assertRaises(NotFound):
                conversation_view(self.rt, other, conv)
            with self.assertRaises(NotFound):
                self.rt.store.delete_conversation(other, conv)
            with self.assertRaises(NotFound):
                await self.chat(other, "продолжу чужой чат", conv=conv, script=[say("x")])
        self.assertEqual(len(self.rt.store.list_conversations(OWNER)), 1)

    async def test_view_shows_trace_cards_and_their_current_status(self):
        final = (await self.chat(OWNER, "создай клиента", script=[call("create_client", name="Демо-ИП История"), say("Подтвердите")]))[-1]
        conv, aid = final["conversation_id"], final["pending_actions"][0]["id"]
        view = conversation_view(self.rt, OWNER, conv)
        user, bot = view["messages"]
        self.assertEqual((user["role"], user["content"], user["files"]), ("user", "создай клиента", []))
        self.assertEqual(bot["trace"], [{"tool": "create_client", "ok": True}])
        self.assertEqual(bot["pending_actions"][0]["status"], "pending")

        res = confirm_action(self.rt, OWNER, aid)
        self.assertEqual(res["message"], "Готово: Создать клиента «Демо-ИП История»")
        view = conversation_view(self.rt, OWNER, conv)
        self.assertEqual(view["messages"][1]["pending_actions"][0]["status"], "confirmed")
        self.assertEqual(view["messages"][-1]["content"], "Готово: Создать клиента «Демо-ИП История»")
        self.assertIn("[Системное уведомление]", self.rt.store.get_conversation(OWNER, conv).messages[-1]["content"])

    async def test_reject_is_shown_in_history(self):
        final = (await self.chat(OWNER, "создай клиента", script=[call("create_client", name="Демо-ИП Отказ"), say("Подтвердите")]))[-1]
        reject_action(self.rt, OWNER, final["pending_actions"][0]["id"])
        view = conversation_view(self.rt, OWNER, final["conversation_id"])
        self.assertEqual(view["messages"][1]["pending_actions"][0]["status"], "rejected")
        self.assertEqual(view["messages"][-1]["content"], "Отменено: Создать клиента «Демо-ИП Отказ»")

    async def test_action_can_be_claimed_only_once(self):
        final = (await self.chat(OWNER, "создай клиента", script=[call("create_client", name="Демо-ИП Дубль"), say("ок")]))[-1]
        aid = final["pending_actions"][0]["id"]
        a1, a2 = self.rt.store.get_pending(OWNER, aid), self.rt.store.get_pending(OWNER, aid)  # «два запроса» видят pending
        self.assertTrue(self.rt.store.claim_pending(a1, "confirmed"))
        self.assertFalse(self.rt.store.claim_pending(a2, "confirmed"))
        with self.assertRaises(Conflict):
            confirm_action(self.rt, OWNER, aid)

    async def test_expired_card(self):
        final = (await self.chat(OWNER, "создай клиента", script=[call("create_client", name="Демо-ИП Поздно"), say("ок")]))[-1]
        self.clock.advance(minutes=16)
        view = conversation_view(self.rt, OWNER, final["conversation_id"])
        self.assertEqual(view["messages"][1]["pending_actions"][0]["status"], "expired")
        with self.assertRaises(Gone):
            confirm_action(self.rt, OWNER, final["pending_actions"][0]["id"])
        self.assertEqual(self.rt.store.get_pending(OWNER, final["pending_actions"][0]["id"]).status, "expired")

    async def test_unexpected_failure_marks_action_failed(self):
        """Сбой при выполнении (например, ошибка БД) не оставляет действие «подтверждённым»."""
        final = (await self.chat(OWNER, "создай клиента", script=[call("create_client", name="Демо-ИП Сбой"), say("ок")]))[-1]
        tool = self.rt.registry.get("create_client")

        def boom(ctx, args):
            raise RuntimeError("duplicate key value violates unique constraint")

        self.rt.registry._tools["create_client"] = dataclasses.replace(tool, handler=boom)
        from app.errors import InternalError
        with self.assertRaises(InternalError):
            confirm_action(self.rt, OWNER, final["pending_actions"][0]["id"])
        view = conversation_view(self.rt, OWNER, final["conversation_id"])
        self.assertEqual(view["messages"][1]["pending_actions"][0]["status"], "failed")
        self.assertTrue(view["messages"][-1]["error"])

    async def test_delete_removes_chat_and_its_actions(self):
        final = (await self.chat(OWNER, "создай клиента", script=[call("create_client", name="Демо-ИП Удалить"), say("ок")]))[-1]
        self.rt.store.delete_conversation(OWNER, final["conversation_id"])
        self.assertEqual(self.rt.store.list_conversations(OWNER), [])
        with self.assertRaises(NotFound):
            confirm_action(self.rt, OWNER, final["pending_actions"][0]["id"])

    async def test_model_failure_is_saved_in_history(self):
        ev = await self.chat(OWNER, "вопрос", script=[])  # модель «упала»
        self.assertEqual(ev[-1]["type"], "error")
        conv = self.rt.store.list_conversations(OWNER)[0]
        view = conversation_view(self.rt, OWNER, conv.id)
        self.assertEqual([m["role"] for m in view["messages"]], ["user", "assistant"])
        self.assertTrue(view["messages"][1]["error"])

    async def test_audit_is_kept_per_company(self):
        await self.chat(OWNER, "что заканчивается", script=[call("list_low_stock"), say("ок")])
        rows = self.rt.store.audit_for_company(1)
        self.assertEqual((rows[0].tool, rows[0].status, rows[0].user_id), ("list_low_stock", "ok", 1))
        self.assertEqual(self.rt.store.audit_for_company(2), [])


class TestHistoryMemory(HistoryContract, unittest.IsolatedAsyncioTestCase):
    backend = "mock"

    def test_uses_memory_store(self):
        self.assertIsInstance(self.rt.store, Store)


@unittest.skipUnless(PG_DSN, "задайте BIZAGENT_TEST_PG, чтобы проверить хранилище на Postgres")
class TestHistoryPostgres(HistoryContract, unittest.IsolatedAsyncioTestCase):
    backend = "postgres"

    def setUp(self):
        reset_pg(PG_DSN)
        super().setUp()

    async def test_history_survives_restart(self):
        final = (await self.chat(OWNER, "создай клиента", script=[call("create_client", name="Демо-ИП Рестарт"), say("Подтвердите")]))[-1]
        conv, aid = final["conversation_id"], final["pending_actions"][0]["id"]

        self.rt = self.runtime([say("Продолжаем")])  # «перезапуск сервера»: новое подключение, пустая память
        self.assertEqual([c.id for c in self.rt.store.list_conversations(OWNER)], [conv])
        self.assertEqual(confirm_action(self.rt, OWNER, aid)["status"], "confirmed")  # карточка из прошлой жизни работает

        await self.chat(OWNER, "что дальше?", conv=conv)
        roles = [m["role"] for m in self.llm.calls[0]["messages"]]
        # модель получила всю историю в правильном порядке: вопрос, вызов, результат, ответ, уведомление, новый вопрос
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "assistant", "user", "user"])
        self.assertEqual(self.llm.calls[0]["messages"][2]["tool_calls"][0]["function"]["name"], "create_client")
        view = conversation_view(self.rt, OWNER, conv)
        self.assertEqual([m["content"] for m in view["messages"]],
                         ["создай клиента", "Подтвердите", "Готово: Создать клиента «Демо-ИП Рестарт»", "что дальше?", "Продолжаем"])
        # в базе каждое сообщение записано ровно один раз (сохраняются только новые сообщения хода)
        again = self.runtime([]).store.get_conversation(OWNER, conv)
        self.assertEqual([m["role"] for m in again.messages], ["user", "assistant", "tool", "assistant", "user", "user", "assistant"])
        self.assertEqual(len(again.display), 5)


if __name__ == "__main__":
    unittest.main()
