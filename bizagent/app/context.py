from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .files import FileStore
    from .kb import KnowledgeBase
    from .mock_data import MockDB


@dataclass(frozen=True)
class Principal:
    """Кто делает запрос. Берётся из токена авторизации на бэкенде, модель его не видит и не может изменить."""

    user_id: int
    company_id: int
    role: str  # owner | manager | accountant
    name: str = ""


@dataclass(frozen=True)
class ToolContext:
    """Всё, что нужно инструменту для работы. Создаётся на бэкенде на каждый вызов."""

    db: "MockDB"
    kb: "KnowledgeBase"
    principal: Principal
    today: date
    files: "FileStore | None" = None  # файлы, приложенные к чату (None — загрузка не настроена)

    @property
    def company_id(self) -> int:
        return self.principal.company_id

    @property
    def role(self) -> str:
        return self.principal.role
