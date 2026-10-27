from __future__ import annotations

from dataclasses import dataclass

from ..clock import Clock
from ..config import Settings
from ..files import FileStore
from ..kb import KnowledgeBase
from ..llm.base import LLMProvider
from ..mock_data import MockDB
from .store import Store
from .tools import ToolRegistry


@dataclass
class Runtime:
    """Все сервисы агента в одном месте. Создаётся один раз при старте приложения."""

    llm: LLMProvider
    db: MockDB
    kb: KnowledgeBase
    registry: ToolRegistry
    store: Store
    clock: Clock
    settings: Settings
    files: FileStore | None = None
