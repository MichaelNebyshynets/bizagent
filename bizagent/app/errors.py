"""Ошибки уровня «агент». Ядро не знает про HTTP: статус лежит в атрибуте,
а в main.py один обработчик переводит их в ответы FastAPI."""
from __future__ import annotations


class AgentError(Exception):
    status = 400
    code = "agent_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(AgentError):
    status = 404
    code = "not_found"


class Forbidden(AgentError):
    status = 403
    code = "forbidden"


class Conflict(AgentError):
    status = 409
    code = "conflict"


class Gone(AgentError):
    status = 410
    code = "expired"


class InternalError(AgentError):
    status = 500
    code = "internal_error"


class Unprocessable(AgentError):
    status = 422
    code = "unprocessable"
