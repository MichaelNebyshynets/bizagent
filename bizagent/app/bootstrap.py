"""Сборка всех частей в один Runtime. Не зависит от FastAPI, поэтому ядро агента можно
запускать и тестировать без веб-сервера."""
from __future__ import annotations

from .agent.runtime import Runtime
from .agent.store import Store
from .agent.tools import build_registry
from .clock import Clock, system_clock
from .config import Settings
from .files import FileStore
from .kb import InMemoryKnowledgeBase, KnowledgeBase
from .llm import build_llm
from .llm.base import LLMProvider
from .mock_data import MockDB, seed


def build_runtime(
    *,
    settings: Settings | None = None,
    llm: LLMProvider | None = None,
    db=None,
    kb=None,
    files: FileStore | None = None,
    clock: Clock | None = None,
) -> Runtime:
    """Любую часть можно подменить (в тестах: ScriptedLLM, MockDB и «замороженные» часы).

    DB_BACKEND=postgres (по умолчанию) — PostgreSQL и база знаний в нём.
    DB_BACKEND=mock — данные в памяти и пустая база знаний: без Docker и Postgres.
    """
    settings = settings or Settings.from_env()
    clock = clock or system_clock
    if settings.db_backend not in ("postgres", "mock"):
        raise RuntimeError(f"Неизвестный DB_BACKEND: {settings.db_backend!r} (нужно postgres или mock)")
    if db is None:
        if settings.db_backend == "mock":
            db = MockDB()
            seed(db, clock().date())
        else:
            from .db_postgres import PostgresDB

            db = PostgresDB(settings.database_url)
    if kb is None:
        kb = InMemoryKnowledgeBase() if settings.db_backend == "mock" else KnowledgeBase(settings.database_url)
    return Runtime(
        llm=llm or build_llm(settings, clock),
        db=db,
        kb=kb,
        registry=build_registry(),
        store=_build_store(settings, clock),
        clock=clock,
        settings=settings,
        files=files or FileStore(settings.upload_dir, clock),
    )


def _build_store(settings: Settings, clock: Clock):
    """История чатов, действия на подтверждении и аудит: в памяти (mock) или в Postgres."""
    if settings.db_backend == "mock":
        return Store(clock, settings.confirm_ttl_min)
    from .agent.pg_store import PostgresStore

    return PostgresStore(settings.database_url, clock, settings.confirm_ttl_min)
