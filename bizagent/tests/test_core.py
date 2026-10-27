"""Тесты ядра агента. Без FastAPI и без настоящей модели: ответы «модели» задаёт ScriptedLLM.
Запуск:  python -m unittest tests.test_core -v     (или pytest tests/test_core.py)

Идея: мы не проверяем, что скажет ИИ (это недетерминированно), а проверяем, что бы он ни сказал,
система остаётся безопасной и корректной: права, изоляция компаний, подтверждения, лимиты.
"""
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta

from app.agent.actions import confirm_action, reject_action
from app.agent.loop import run_agent_events
from app.agent.tools import (
    CompareArgs, CreateOrderArgs, FindClientArgs, OrderLine, ProductHistoryArgs, ToolError, build_registry,
)
from app.bootstrap import build_runtime
from app.clock import MINSK
from app.config import Settings
from app.context import Principal, ToolContext
from app.errors import Conflict, Forbidden, Gone, NotFound, Unprocessable
from app.kb import InMemoryKnowledgeBase
from app.llm.base import LLMResponse, ToolCall
from app.llm.mock import ScriptedLLM, call, say

TODAY = date(2026, 10, 11)
OWNER = Principal(1, 1, "owner", "Владелец")
MANAGER = Principal(2, 1, "manager", "Менеджер")
ACCOUNTANT = Principal(3, 1, "accountant", "Бухгалтер")
FLORA = Principal(4, 2, "owner", "Владелец Флоры")


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 11, 12, 0, tzinfo=MINSK)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


class Base(unittest.IsolatedAsyncioTestCase):
    def make(self, script=None, kb=None, **settings):
        self.clock = FakeClock()
        self.llm = ScriptedLLM(script or [])
        # Тесты ядра не зависят от Postgres: данные в памяти (DB_BACKEND=mock), файлы во временной папке
        tmp = tempfile.mkdtemp(prefix="bizagent-test-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.rt = build_runtime(settings=Settings(db_backend="mock", upload_dir=tmp, **settings), llm=self.llm, clock=self.clock, kb=kb)
        return self.rt

    async def chat(self, principal, text="вопрос", conv=None):
        return [e async for e in run_agent_events(self.rt, principal, conv, text)]

    def ctx(self, principal):
        return ToolContext(self.rt.db, self.rt.kb, principal, TODAY)

    def pid(self, sku):
        return next(p.id for p in self.rt.db.products(1) if p.sku == sku)

    def audit(self, status=None):
        return [r for r in self.rt.store.audit_log if status is None or r.status == status]


# ===================================================================== цикл агента


class TestLoop(Base):
    async def test_read_tool_flow(self):
        self.make([call("get_sales_summary", date_from="2026-09-01", date_to="2026-09-30"), say("Выручка посчитана.")])
        ev = await self.chat(OWNER, "Сколько продали в сентябре?")
        self.assertEqual([e["type"] for e in ev], ["tool_call", "tool_result", "final"])
        self.assertTrue(ev[1]["ok"])
        self.assertEqual(ev[-1]["message"], "Выручка посчитана.")
        # на втором шаге модель получила результат инструмента
        last = self.llm.calls[1]["messages"][-1]
        self.assertEqual(last["role"], "tool")
        self.assertIn('"revenue"', last["content"])
        # системный промпт: актуальная дата, компания, роль
        sys_prompt = self.llm.calls[0]["messages"][0]["content"]
        for part in ("2026-10-11", "Уютный дом", "владелец"):
            self.assertIn(part, sys_prompt)
        self.assertEqual(self.audit("ok")[0].tool, "get_sales_summary")

    async def test_model_cannot_inject_company_id(self):
        self.make([call("get_sales_summary", date_from="2026-09-01", date_to="2026-09-30", company_id=2), say("ок")])
        ev = await self.chat(OWNER)
        self.assertFalse(ev[1]["ok"])
        self.assertIn("Неверные аргументы", ev[1]["preview"])
        self.assertEqual(self.audit()[0].status, "error")

    async def test_unknown_tool(self):
        self.make([call("drop_database"), say("ок")])
        ev = await self.chat(OWNER)
        self.assertFalse(ev[1]["ok"])
        self.assertIn("Неизвестный инструмент", ev[1]["preview"])

    async def test_invalid_json_arguments_fed_back_to_model(self):
        bad = LLMResponse(tool_calls=[ToolCall(id="c1", name="list_low_stock", arguments_error="невалидный JSON", raw_arguments="{oops")])
        self.make([bad, say("исправился")])
        ev = await self.chat(OWNER)
        self.assertFalse(ev[1]["ok"])
        # в историю для сервера модели попадает безопасный "{}", а не мусорная строка
        assistant = self.llm.calls[1]["messages"][-2]
        self.assertEqual(assistant["tool_calls"][0]["function"]["arguments"], "{}")

    async def test_max_steps_guard(self):
        self.make([call("list_low_stock") for _ in range(10)], max_steps=3)
        ev = await self.chat(OWNER)
        self.assertTrue(ev[-1].get("truncated"))
        self.assertEqual(len(self.llm.calls), 3)  # модель вызвана ровно max_steps раз, а не бесконечно

    async def test_llm_failure_is_reported_not_raised(self):
        self.make([])  # сценарий пуст, ScriptedLLM бросит LLMError
        ev = await self.chat(OWNER)
        self.assertEqual(ev[-1]["type"], "error")

    async def test_too_many_calls_in_one_step(self):
        many = LLMResponse(tool_calls=[ToolCall(id=f"c{i}", name="list_low_stock") for i in range(10)])
        self.make([many, say("ок")])
        ev = await self.chat(OWNER)
        results = [e["ok"] for e in ev if e["type"] == "tool_result"]
        self.assertEqual(results, [True] * 8 + [False] * 2)
        # на КАЖДЫЙ tool_call есть ответ tool (иначе история невалидна для сервера модели)
        msgs = self.llm.calls[1]["messages"]
        self.assertEqual(len([m for m in msgs if m["role"] == "tool"]), 10)

    async def test_history_is_kept_between_turns(self):
        self.make([say("первый"), say("второй")])
        conv = (await self.chat(OWNER, "один"))[-1]["conversation_id"]
        await self.chat(OWNER, "два", conv=conv)
        roles = [m["role"] for m in self.llm.calls[1]["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])


# ===================================================================== изоляция компаний


class TestIsolation(Base):
    def setUp(self):
        self.make()

    def test_other_company_cannot_find_my_client(self):
        find = self.rt.registry.get("find_client").handler
        self.assertEqual(find(self.ctx(OWNER), FindClientArgs(query="Ковалёв"))["clients"][0]["name"], "Алексей Ковалёв")
        self.assertEqual(find(self.ctx(FLORA), FindClientArgs(query="Ковалёв"))["clients"], [])

    def test_other_company_cannot_use_my_product(self):
        tool = self.rt.registry.get("create_order")
        args = CreateOrderArgs(items=[OrderLine(product_id=self.pid("PS-002"), qty=1)])
        with self.assertRaises(ToolError):
            tool.summarize(self.ctx(FLORA), args)

    def test_other_company_cannot_read_my_product_history(self):
        tool = self.rt.registry.get("get_product_sales_history")
        with self.assertRaises(ToolError):
            tool.handler(self.ctx(FLORA), ProductHistoryArgs(product_id=self.pid("TX-001"), date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)))

    async def test_foreign_conversation_looks_nonexistent(self):
        self.make([say("привет")])
        conv = (await self.chat(OWNER))[-1]["conversation_id"]
        with self.assertRaises(NotFound):
            await self.chat(FLORA, conv=conv)
        with self.assertRaises(NotFound):  # даже коллега из той же компании не читает чужой диалог
            await self.chat(MANAGER, conv=conv)


# ===================================================================== роли


class TestRoles(Base):
    def setUp(self):
        self.make()

    def test_tools_hidden_by_role(self):
        reg = self.rt.registry
        self.assertIn("get_profit_summary", reg.names_for("owner"))
        for hidden in ("get_profit_summary", "record_expense"):
            self.assertNotIn(hidden, reg.names_for("manager"))
        for hidden in ("create_order", "create_client"):
            self.assertNotIn(hidden, reg.names_for("accountant"))
        self.assertEqual(len(reg.schemas_for("manager")), len(reg.names_for("manager")))

    async def test_denied_even_if_model_calls_hidden_tool(self):
        self.make([call("get_profit_summary", date_from="2026-09-01", date_to="2026-09-30"), say("нет прав")])
        ev = await self.chat(MANAGER)
        self.assertFalse(ev[1]["ok"])
        self.assertEqual(self.audit()[0].status, "denied")

    async def test_accountant_cannot_create_order(self):
        self.make([call("create_order", items=[{"product_id": 1, "qty": 1}]), say("нет прав")])
        ev = await self.chat(ACCOUNTANT)
        self.assertFalse(ev[1]["ok"])
        self.assertEqual(ev[-1]["pending_actions"], [])

    def test_manager_cannot_see_margin(self):
        top = self.rt.registry.get("get_top_products").handler
        from app.agent.tools import TopProductsArgs
        a = TopProductsArgs(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30), metric="profit")
        with self.assertRaises(ToolError):
            top(self.ctx(MANAGER), a)
        self.assertEqual(top(self.ctx(OWNER), a)["metric"], "profit")
        # и себестоимость товара менеджеру не показывается
        find = self.rt.registry.get("find_product").handler
        from app.agent.tools import FindProductArgs
        self.assertNotIn("cost", find(self.ctx(MANAGER), FindProductArgs(query="Плед"))["products"][0])
        self.assertIn("cost", find(self.ctx(OWNER), FindProductArgs(query="Плед"))["products"][0])


# ===================================================================== подтверждение действий


class TestConfirmation(Base):
    async def propose_client(self, principal=MANAGER, **kw):
        self.make([call("create_client", **({"name": "Демо-ИП Тест", "unp": "000000777"} | kw)), say("Подготовил, подтвердите.")])
        ev = await self.chat(principal, "создай клиента")
        return ev[-1]

    def has_client(self, name="Демо-ИП Тест"):
        return any(c.name == name for c in self.rt.db.clients(1))

    async def test_write_requires_confirmation(self):
        final = await self.propose_client()
        self.assertEqual(len(final["pending_actions"]), 1)
        self.assertFalse(self.has_client(), "до подтверждения данные меняться не должны")
        res = confirm_action(self.rt, MANAGER, final["pending_actions"][0]["id"])
        self.assertEqual(res["status"], "confirmed")
        self.assertTrue(self.has_client())
        self.assertEqual([r.status for r in self.audit() if r.tool == "create_client"], ["pending", "confirmed"])

    async def test_double_confirm_does_not_duplicate(self):
        aid = (await self.propose_client())["pending_actions"][0]["id"]
        confirm_action(self.rt, MANAGER, aid)
        with self.assertRaises(Conflict):
            confirm_action(self.rt, MANAGER, aid)
        self.assertEqual(sum(c.name == "Демо-ИП Тест" for c in self.rt.db.clients(1)), 1)

    async def test_reject(self):
        aid = (await self.propose_client())["pending_actions"][0]["id"]
        self.assertEqual(reject_action(self.rt, MANAGER, aid)["status"], "rejected")
        self.assertFalse(self.has_client())
        with self.assertRaises(Conflict):
            confirm_action(self.rt, MANAGER, aid)

    async def test_only_author_can_confirm(self):
        aid = (await self.propose_client())["pending_actions"][0]["id"]
        for other in (OWNER, FLORA):  # даже владелец той же компании не может подтвердить чужое действие
            with self.assertRaises(NotFound):
                confirm_action(self.rt, other, aid)
        self.assertFalse(self.has_client())

    async def test_confirmation_expires(self):
        aid = (await self.propose_client())["pending_actions"][0]["id"]
        self.clock.advance(minutes=16)
        with self.assertRaises(Gone):
            confirm_action(self.rt, MANAGER, aid)
        self.assertFalse(self.has_client())

    async def test_role_rechecked_at_confirmation(self):
        aid = (await self.propose_client())["pending_actions"][0]["id"]
        demoted = Principal(MANAGER.user_id, MANAGER.company_id, "accountant")  # роль изменили, пока действие ждало
        with self.assertRaises(Forbidden):
            confirm_action(self.rt, demoted, aid)

    async def test_duplicate_unp_rejected_before_asking_user(self):
        self.make([call("create_client", name="Другая Альфа", unp="000000101"), say("уже есть")])
        ev = await self.chat(MANAGER)
        self.assertFalse(ev[1]["ok"])
        self.assertEqual(ev[-1]["pending_actions"], [])

    async def test_system_note_added_after_confirmation(self):
        final = await self.propose_client()
        confirm_action(self.rt, MANAGER, final["pending_actions"][0]["id"])
        last = self.rt.store.get_conversation(MANAGER, final["conversation_id"]).messages[-1]
        self.assertIn("[Системное уведомление]", last["content"])
        self.assertIn("Выполнено", last["content"])

    async def test_order_flow_and_stock(self):
        self.make()
        mug = self.pid("PS-002")  # кружка 6.90, на складе 90
        self.llm.script = [call("create_order", items=[{"product_id": mug, "qty": 3}]), say("подтвердите")]
        final = (await self.chat(MANAGER))[-1]
        self.assertIn("20.70", final["pending_actions"][0]["summary"])
        res = confirm_action(self.rt, MANAGER, final["pending_actions"][0]["id"])
        self.assertEqual(res["result"]["total"], 20.70)
        self.assertEqual(self.rt.db.product(1, mug).stock, 87)

    async def test_stock_rechecked_at_confirmation(self):
        self.make()
        pan = self.pid("PS-003")  # сковорода, на складе 3
        self.llm.script = [call("create_order", items=[{"product_id": pan, "qty": 3}]), say("подтвердите")]
        aid = (await self.chat(MANAGER))[-1]["pending_actions"][0]["id"]
        self.rt.db.product(1, pan).stock = 1  # пока пользователь думал, кто-то продал
        with self.assertRaises(Unprocessable):
            confirm_action(self.rt, MANAGER, aid)
        self.assertEqual(self.rt.db.product(1, pan).stock, 1)
        self.assertIn("failed", [r.status for r in self.audit()])

    async def test_expense_flow_and_validation(self):
        self.make([call("record_expense", category="Аренда", amount=12.345), call("record_expense", category="Аренда", amount=1200, day="2026-10-01"), say("подтвердите")])
        ev = await self.chat(ACCOUNTANT)
        self.assertFalse(ev[1]["ok"], "3 знака после запятой должны отклоняться")
        aid = ev[-1]["pending_actions"][0]["id"]
        before = len(self.rt.db.expenses(1, date(2026, 10, 1), TODAY))
        confirm_action(self.rt, ACCOUNTANT, aid)
        self.assertEqual(len(self.rt.db.expenses(1, date(2026, 10, 1), TODAY)), before + 1)


# ===================================================================== «сюжет» в данных и база знаний


class TestDataStory(Base):
    def setUp(self):
        self.make()

    def test_september_drop_is_explained_by_the_plaid(self):
        res = self.rt.registry.get("compare_periods").handler(
            self.ctx(OWNER), CompareArgs(base_from=date(2026, 8, 1), base_to=date(2026, 8, 31), compare_from=date(2026, 9, 1), compare_to=date(2026, 9, 30)))
        self.assertLess(res["delta"]["revenue"], 0)
        self.assertIn("Плед", res["biggest_drops"][0]["name"])
        hist = self.rt.registry.get("get_product_sales_history").handler(
            self.ctx(OWNER), ProductHistoryArgs(product_id=self.pid("TX-001"), date_from=date(2026, 8, 1), date_to=date(2026, 10, 11)))
        streak = hist["zero_sales_streaks"][0]
        self.assertGreaterEqual(streak["days"], 18)
        self.assertEqual(streak["from"], "2026-09-05")

    def test_slow_movers_and_low_stock(self):
        slow = self.rt.registry.get("list_slow_movers").handler(self.ctx(OWNER), type("A", (), {"days": 90})())
        self.assertEqual({p["name"] for p in slow["products"]}, {"Часы настенные ретро", "Подсвечник латунный"})
        low = self.rt.registry.get("list_low_stock").handler(self.ctx(OWNER), type("A", (), {"threshold": 5})())
        self.assertEqual({p["name"] for p in low["products"]}, {"Сковорода 26 см", "Чайник эмалированный", "Гирлянда светодиодная"})

    def test_seed_is_deterministic(self):
        def total():
            rt = build_runtime(settings=Settings(db_backend="mock"), llm=ScriptedLLM([]), clock=FakeClock())
            return sum(i.qty * i.price for o in rt.db.orders(1, date(2025, 1, 1), TODAY) for i in o.items)
        self.assertEqual(total(), total())

    def test_knowledge_base_empty_means_no_answer(self):
        from app.agent.tools import KbSearchArgs
        res = self.rt.registry.get("search_knowledge_base").handler(self.ctx(OWNER), KbSearchArgs(query="какой налог платит ИП"))
        self.assertEqual(res["results"], [])
        self.assertIn("Не отвечай по памяти", res["note"])

    def test_knowledge_base_returns_source_and_date(self):
        from app.agent.tools import KbSearchArgs
        kb = InMemoryKnowledgeBase()
        kb.add(title="Тестовый документ", source_url="https://example.com/doc", doc_date="2026-01-01", text="Первый абзац про отчётность.\n\nВторой абзац про регистрацию предпринимателей.")
        self.make(kb=kb)
        res = self.rt.registry.get("search_knowledge_base").handler(self.ctx(OWNER), KbSearchArgs(query="регистрация предпринимателя"))
        self.assertEqual(res["results"][0]["source_url"], "https://example.com/doc")
        self.assertEqual(res["results"][0]["doc_date"], "2026-01-01")


class TestSchemas(unittest.TestCase):
    def test_schemas_are_flat_and_never_ask_for_identity(self):
        reg = build_registry()
        for role in ("owner", "manager", "accountant"):
            for schema in reg.schemas_for(role):
                dumped = json.dumps(schema)
                self.assertNotIn("$ref", dumped)
                self.assertNotIn("company_id", dumped, "модель не должна даже знать про company_id")
                self.assertNotIn("user_id", dumped)


class TestDemoMockLLM(Base):
    async def test_end_to_end_without_scripted_llm(self):
        self.clock = FakeClock()
        self.rt = build_runtime(settings=Settings(db_backend="mock"), clock=self.clock)  # настоящая MockLLM
        ev = await self.chat(OWNER, "Какие товары заканчиваются?")
        self.assertEqual([e["type"] for e in ev], ["tool_call", "tool_result", "final"])
        self.assertIn("Сковорода", ev[-1]["message"])


if __name__ == "__main__":
    unittest.main()
