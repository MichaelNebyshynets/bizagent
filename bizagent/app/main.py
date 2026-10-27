# ВАЖНО: в этом файле намеренно НЕТ `from __future__ import annotations`:
# FastAPI разбирает аннотации параметров во время выполнения, и с отложенными аннотациями
# модели/зависимости, объявленные не на уровне модуля, могут не разрешаться.
"""HTTP-слой. Тонкая обёртка над ядром агента: авторизация → вызов ядра → JSON/SSE.
Здесь нет бизнес-логики: вся она в app/agent/*.
"""
import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .agent.actions import confirm_action, reject_action
from .agent.loop import conversation_view, run_agent_events
from .agent.runtime import Runtime
from .auth import principal_from_token
from .bootstrap import build_runtime
from .clock import Clock
from .config import Settings
from .context import Principal
from .errors import AgentError
from .files import MAX_FILE_BYTES, FileStore, FileTooLarge
from .kb import KnowledgeBase
from .llm.base import LLMProvider
from .mock_data import MockDB

router = APIRouter(prefix="/agent", tags=["agent"])

# ---------------------------------------------------------------- зависимости

def get_runtime(request: Request) -> Runtime:
    return request.app.state.rt

def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    """Кто делает запрос. ЗАГЛУШКА: см. app/auth.py (в реальной системе здесь разбор JWT)."""
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    principal = principal_from_token(token)
    if principal is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация", headers={"WWW-Authenticate": "Bearer"})
    return principal

class ChatRequest(BaseModel):
    message: str

# ---------------------------------------------------------------- модели запросов

class ChatIn(BaseModel):
    conversation_id: str | None = Field(default=None, description="id диалога; не указан — начнётся новый")
    message: str = Field(min_length=1, max_length=4000)
    file_ids: list[str] = Field(default_factory=list, max_length=5, description="файлы из /agent/upload, приложенные к этому сообщению")

class LoginIn(BaseModel):
    email: str

# ---------------------------------------------------------------- эндпоинты



@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form("Все"),
    principal: Principal = Depends(get_principal),
    rt: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    """Загрузить файл в чат. Возвращает file_id: его нужно передать в file_ids следующего сообщения /agent/chat.
    Файл виден только загрузившему его пользователю в его компании."""
    data = await file.read(MAX_FILE_BYTES + 1)  # читаем не больше лимита + 1 байт, чтобы не держать в памяти огромный файл
    if len(data) > MAX_FILE_BYTES:
        raise FileTooLarge(f"Файл больше {MAX_FILE_BYTES // (1024 * 1024)} МБ.")
    # Разбор PDF/XLSX может занять время: выполняем в пуле потоков, чтобы не блокировать сервер
    sf = await run_in_threadpool(rt.files.save, principal, file.filename, data, category)
    rt.store.log(principal, None, "upload_file", {"filename": sf.filename, "size": sf.size}, "ok", sf.id)
    return {
        "status": "success",
        **sf.public(),
        "message": f"Файл «{sf.filename}» загружен ({sf.chars} символов текста)."
        + (" Текст обрезан: агент прочитает только начало." if sf.truncated else ""),
    }


@router.get("/files")
def list_files(principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> list[dict[str, Any]]:
    return [f.public() for f in rt.files.list(principal)]


@router.delete("/files/{file_id}")
def delete_file(file_id: str, principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    rt.files.delete(principal, file_id)  # NotFound (404), если файл чужой или его нет
    rt.store.log(principal, None, "delete_file", {"file_id": file_id}, "ok")
    return {"status": "deleted", "file_id": file_id}

@router.post("/chat")
async def chat(body: ChatIn, principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    """Обычный (не потоковый) ответ: ждём, пока агент закончит, и отдаём результат целиком."""
    trace: dict[str, dict[str, Any]] = {}
    final: dict[str, Any] | None = None
    async for ev in run_agent_events(rt, principal, body.conversation_id, body.message, body.file_ids):
        kind = ev["type"]
        if kind == "tool_call":
            trace[ev["id"]] = {"tool": ev["name"], "args": ev["args"], "ok": None}
        elif kind == "tool_result":
            trace[ev["id"]]["ok"] = ev["ok"]
        elif kind == "error":
            raise HTTPException(status_code=502, detail=ev["message"])
        elif kind == "final":
            final = ev
    if final is None:
        raise HTTPException(status_code=500, detail="Агент не вернул ответ")
    return {**{k: v for k, v in final.items() if k != "type"}, "trace": list(trace.values())}

def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

@router.post("/chat/stream")
async def chat_stream(body: ChatIn, principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)):
    """Server-Sent Events: фронтенд получает события по мере работы агента
    (tool_call → tool_result → pending_action → final). Потокенный вывод текста добавим следующим шагом."""

    async def gen() -> AsyncIterator[str]:
        try:
            async for ev in run_agent_events(rt, principal, body.conversation_id, body.message, body.file_ids):
                yield _sse(ev)
        except AgentError as e:  # после начала стрима статус ответа уже не изменить, поэтому ошибка уходит событием
            yield _sse({"type": "error", "message": e.message, "code": e.code})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.post("/actions/{action_id}/confirm")
def confirm(action_id: str, principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    return confirm_action(rt, principal, action_id)

@router.post("/actions/{action_id}/reject")
def reject(action_id: str, principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    return reject_action(rt, principal, action_id)

@router.get("/conversations")
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200), principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)
) -> list[dict[str, Any]]:
    """Чаты текущего пользователя, новые сверху: id, title, created_at, updated_at."""
    return [c.info() for c in rt.store.list_conversations(principal, limit)]


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    """Чат так, как его видит пользователь: вопросы, ответы, вызванные инструменты, карточки с текущим статусом."""
    return conversation_view(rt, principal, conversation_id)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    rt.store.delete_conversation(principal, conversation_id)  # NotFound (404), если чат чужой
    return {"status": "deleted", "id": conversation_id}

@router.get("/tools")
def list_tools(principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    return {"role": principal.role, "tools": rt.registry.names_for(principal.role)}

@router.get("/audit")
def audit(limit: int = Query(default=50, ge=1, le=200), principal: Principal = Depends(get_principal), rt: Runtime = Depends(get_runtime)) -> list[dict[str, Any]]:
    """Журнал вызовов инструментов компании. Только для владельца."""
    if principal.role != "owner":
        raise HTTPException(status_code=403, detail="Только для владельца")
    return [
        {
            "ts": r.ts.isoformat(), "user_id": r.user_id, "role": r.role, "conversation_id": r.conversation_id,
            "tool": r.tool, "args": r.args, "status": r.status, "detail": r.detail,
        }
        for r in rt.store.audit_for_company(principal.company_id, limit)
    ]

# ---------------------------------------------------------------- приложение

def create_app(
    *,
    settings: Settings | None = None,
    llm: LLMProvider | None = None,
    db: MockDB | None = None,
    kb: KnowledgeBase | None = None,
    files: FileStore | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    rt = build_runtime(settings=settings, llm=llm, db=db, kb=kb, files=files, clock=clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        aclose = getattr(rt.llm, "aclose", None)  # закрываем HTTP-клиент провайдера модели
        if aclose is not None:
            await aclose()
        close = getattr(rt.store, "close", None)  # пул подключений к Postgres
        if close is not None:
            close()

    app = FastAPI(title="BizAgent: ИИ-агент для МСБ РБ", lifespan=lifespan)
    app.state.rt = rt

    # React-фронтенд на другом порту (Vite 5173, CRA 3000) без CORS не сможет обращаться к API
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(AgentError)
    async def agent_error_handler(_: Request, exc: AgentError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"detail": exc.message, "code": exc.code})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "llm": rt.settings.llm_provider, "db": rt.settings.db_backend}

    app.include_router(router)
    return app

app = create_app()

@app.post("/auth/login")
def login(body: LoginIn, rt: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    """Вход по email с возвратом JWT-токена."""
    from .auth import create_access_token
    
    clean_email = body.email.strip().lower()
    if not hasattr(rt.db, "_get_conn"):
        raise HTTPException(status_code=503, detail="Вход по email работает только с Postgres (DB_BACKEND=postgres). В режиме mock используйте демо-токен.")

    with rt.db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, company_id, role, name FROM users WHERE LOWER(email) = LOWER(%s);", 
                (clean_email,)
            )
            user = cur.fetchone()
            
            if not user:
                # Если пользователя нет в базе — бросаем 404
                raise HTTPException(status_code=404, detail=f"Пользователь '{clean_email}' не найден в БД")
            
            uid, cid, role, name = user
            token = create_access_token(user_id=uid, company_id=cid, role=role, name=name)
            return {"access_token": token, "token_type": "bearer", "role": role, "name": name}

