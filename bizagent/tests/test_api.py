"""Тесты HTTP-слоя. Требуют: pip install -r requirements.txt. Без FastAPI файл просто пропускается.
Работают без Postgres (DB_BACKEND=mock) и без настоящей модели (ScriptedLLM).
"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import atexit  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.clock import MINSK  # noqa: E402
from app.config import Settings  # noqa: E402
from app.llm.mock import ScriptedLLM, call, say  # noqa: E402
from app.main import create_app  # noqa: E402

OWNER = {"Authorization": "Bearer demo-owner-uyut"}
MANAGER = {"Authorization": "Bearer demo-manager-uyut"}
FLORA = {"Authorization": "Bearer demo-owner-flora"}


def make(script):
    upload_dir = tempfile.mkdtemp(prefix="bizagent-api-")
    atexit.register(shutil.rmtree, upload_dir, True)
    llm = ScriptedLLM(script)
    settings = Settings(db_backend="mock", upload_dir=upload_dir)
    app = create_app(settings=settings, llm=llm, clock=lambda: datetime(2026, 10, 11, 12, 0, tzinfo=MINSK))
    return TestClient(app), app.state.rt


def post_chat(client, headers, text="вопрос", conv=None):
    return client.post("/agent/chat", json={"message": text, "conversation_id": conv}, headers=headers)


def test_health():
    client, _ = make([])
    assert client.get("/health").json()["status"] == "ok"


def test_requires_auth():
    client, _ = make([])
    assert post_chat(client, {}).status_code == 401
    assert post_chat(client, {"Authorization": "Bearer wrong"}).status_code == 401


def test_chat_returns_message_and_trace():
    client, _ = make([call("list_low_stock"), say("Заканчиваются три товара.")])
    body = post_chat(client, OWNER).json()
    assert body["message"] == "Заканчиваются три товара."
    assert body["trace"] == [{"tool": "list_low_stock", "args": {}, "ok": True}]


def test_confirm_flow_over_http():
    client, rt = make([call("create_client", name="Демо-ИП Тест"), say("Подтвердите.")])
    body = post_chat(client, MANAGER).json()
    action_id = body["pending_actions"][0]["id"]
    assert not any(c.name == "Демо-ИП Тест" for c in rt.db.clients(1))

    assert client.post(f"/agent/actions/{action_id}/confirm", headers=FLORA).status_code == 404  # чужая компания
    assert client.post(f"/agent/actions/{action_id}/confirm", headers=OWNER).status_code == 404  # не автор
    assert client.post(f"/agent/actions/{action_id}/confirm", headers=MANAGER).status_code == 200
    assert client.post(f"/agent/actions/{action_id}/confirm", headers=MANAGER).status_code == 409  # повтор
    assert any(c.name == "Демо-ИП Тест" for c in rt.db.clients(1))


def test_audit_is_owner_only():
    client, _ = make([call("list_low_stock"), say("ок")])
    post_chat(client, MANAGER)
    assert client.get("/agent/audit", headers=MANAGER).status_code == 403
    rows = client.get("/agent/audit", headers=OWNER).json()
    assert rows[0]["tool"] == "list_low_stock" and rows[0]["status"] == "ok"
    assert client.get("/agent/audit", headers=FLORA).json() == []  # журнал другой компании пуст


def test_foreign_conversation_is_404():
    client, _ = make([say("привет")])
    conv = post_chat(client, OWNER).json()["conversation_id"]
    assert client.get(f"/agent/conversations/{conv}", headers=OWNER).status_code == 200
    assert client.get(f"/agent/conversations/{conv}", headers=FLORA).status_code == 404
    assert post_chat(client, FLORA, conv=conv).status_code == 404


def test_stream_sends_events_and_final():
    client, _ = make([call("list_low_stock"), say("Готово.")])
    r = client.post("/agent/chat/stream", json={"message": "что заканчивается?"}, headers=OWNER)
    assert r.headers["content-type"].startswith("text/event-stream")
    assert '"type": "tool_call"' in r.text and '"type": "final"' in r.text


# ------------------------------------------------------------------ загрузка файлов


def upload(client, headers, name="sales.csv", data="товар;выручка\nПлед;39.90\n".encode(), category="Продажи"):
    return client.post("/agent/upload", files={"file": (name, data)}, data={"category": category}, headers=headers)


def read_attached_file(messages):
    """«Модель», которая читает файл, приложенный к последнему сообщению пользователя."""
    fid = re.search(r"file_id=([0-9a-f]{32})", messages[-1]["content"]).group(1)
    return call("read_uploaded_file", file_id=fid)


def test_upload_requires_auth():
    client, _ = make([])
    assert upload(client, {}).status_code == 401


def test_upload_then_chat_reads_file():
    client, _ = make([read_attached_file, say("В файле одна строка продаж.")])
    up = upload(client, OWNER)
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["filename"] == "sales.csv" and body["category"] == "Продажи" and len(body["file_id"]) == 32
    r = client.post("/agent/chat", json={"message": "Что в файле?", "file_ids": [body["file_id"]]}, headers=OWNER)
    assert r.status_code == 200, r.text
    assert r.json()["trace"] == [{"tool": "read_uploaded_file", "args": {"file_id": body["file_id"]}, "ok": True}]


def test_foreign_file_is_404_everywhere():
    client, _ = make([say("не должен вызываться")])
    fid = upload(client, OWNER).json()["file_id"]
    assert client.post("/agent/chat", json={"message": "прочитай", "file_ids": [fid]}, headers=FLORA).status_code == 404
    assert client.post("/agent/chat", json={"message": "прочитай", "file_ids": [fid]}, headers=MANAGER).status_code == 404
    assert client.get("/agent/files", headers=FLORA).json() == []
    assert client.delete(f"/agent/files/{fid}", headers=FLORA).status_code == 404
    assert [f["file_id"] for f in client.get("/agent/files", headers=OWNER).json()] == [fid]


def test_upload_rejects_bad_files():
    client, _ = make([])
    assert upload(client, OWNER, name="virus.exe", data=b"MZ").status_code == 415
    assert upload(client, OWNER, name="empty.txt", data=b"").status_code == 422
    big = upload(client, OWNER, name="big.txt", data=b"a" * (10 * 1024 * 1024 + 1))
    assert big.status_code == 413 and big.json()["code"] == "file_too_large"
    assert client.get("/agent/files", headers=OWNER).json() == []


def test_filename_cannot_escape_upload_dir():
    client, rt = make([])
    r = upload(client, OWNER, name="../../evil.txt", data=b"x")
    assert r.status_code == 200 and r.json()["filename"] == "evil.txt"
    root = Path(rt.files.root)
    assert not (root.parent / "evil.txt").exists() and not (root.parent.parent / "evil.txt").exists()
    assert all(p.resolve().is_relative_to(root.resolve()) for p in root.rglob("*"))


def test_delete_file_and_audit():
    client, _ = make([])
    fid = upload(client, OWNER).json()["file_id"]
    assert client.delete(f"/agent/files/{fid}", headers=OWNER).status_code == 200
    assert client.get("/agent/files", headers=OWNER).json() == []
    assert [r["tool"] for r in client.get("/agent/audit", headers=OWNER).json()] == ["delete_file", "upload_file"]


def test_too_many_files_in_one_message():
    client, _ = make([])
    r = client.post("/agent/chat", json={"message": "x", "file_ids": ["0" * 32] * 6}, headers=OWNER)
    assert r.status_code == 422


# ------------------------------------------------------------------ история чатов


def test_conversations_list_view_and_delete_are_per_user():
    client, _ = make([say("Ответ 1"), call("create_client", name="Демо-ИП API"), say("Подтвердите")])
    c1 = post_chat(client, OWNER, "Первый вопрос").json()["conversation_id"]
    body = post_chat(client, OWNER, "Создай клиента").json()
    c2, aid = body["conversation_id"], body["pending_actions"][0]["id"]
    assert client.post(f"/agent/actions/{aid}/confirm", headers=OWNER).json()["message"] == "Готово: Создать клиента «Демо-ИП API»"

    chats = client.get("/agent/conversations", headers=OWNER).json()
    assert {c["id"] for c in chats} == {c1, c2} and {c["title"] for c in chats} == {"Первый вопрос", "Создай клиента"}
    view = client.get(f"/agent/conversations/{c2}", headers=OWNER).json()
    assert [m["role"] for m in view["messages"]] == ["user", "assistant", "assistant"]
    assert view["messages"][1]["pending_actions"][0]["status"] == "confirmed"
    assert view["messages"][1]["trace"] == [{"tool": "create_client", "ok": True}]

    for other in (MANAGER, FLORA):  # роль и компания: чужие чаты не видны и не удаляются
        assert client.get("/agent/conversations", headers=other).json() == []
        assert client.get(f"/agent/conversations/{c1}", headers=other).status_code == 404
        assert client.delete(f"/agent/conversations/{c1}", headers=other).status_code == 404

    assert client.delete(f"/agent/conversations/{c1}", headers=OWNER).status_code == 200
    assert [c["id"] for c in client.get("/agent/conversations", headers=OWNER).json()] == [c2]
