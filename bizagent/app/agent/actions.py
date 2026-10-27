"""Подтверждение и отклонение действий. Это отдельные HTTP-запросы пользователя (кнопки в UI),
МОДЕЛЬ в них не участвует: она не может «подтвердить» за пользователя."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from ..context import Principal, ToolContext
from ..errors import Conflict, Forbidden, Gone, InternalError, Unprocessable
from .loop import format_validation_error
from .runtime import Runtime
from .store import PendingAction
from .tools import ToolError

logger = logging.getLogger("agent.actions")


def _note(rt: Runtime, act: PendingAction, text: str, shown: str, error: bool = False) -> None:
    """Сообщаем модели в истории диалога, что произошло (чтобы на следующем вопросе она не «думала», что действие
    ещё висит), и добавляем строку в чат пользователя (чтобы она осталась в истории после перезагрузки)."""
    display = {"role": "assistant", "content": shown, **({"error": True} if error else {})}
    rt.store.add_system_note(act.conversation_id, text, display)


def confirm_action(rt: Runtime, principal: Principal, action_id: str) -> dict[str, Any]:
    act = rt.store.get_pending(principal, action_id)  # NotFound, если чужое
    log = lambda status, detail="": rt.store.log(principal, act.conversation_id, act.tool_name, act.args, status, detail)  # noqa: E731

    if act.status != "pending":
        raise Conflict(f"Действие уже обработано (статус: {act.status}).")
    if rt.clock() > act.expires_at:
        if rt.store.claim_pending(act, "expired"):
            log("expired")
        raise Gone("Время подтверждения истекло. Попросите агента повторить действие.")

    tool = rt.registry.get(act.tool_name)
    if tool is None or principal.role not in tool.roles:  # роль могли изменить, пока действие ждало
        log("denied", f"роль {principal.role}")
        raise Forbidden("Недостаточно прав для этого действия.")

    # «Занимаем» действие ДО выполнения, атомарно: повторное нажатие «Подтвердить» (двойной клик, повтор запроса,
    # второй сервер) получит 409 и не создаст дубликат.
    if not rt.store.claim_pending(act, "confirmed"):
        raise Conflict("Действие уже обработано.")
    ctx = ToolContext(db=rt.db, kb=rt.kb, principal=principal, today=rt.clock().date(), files=rt.files)
    try:
        result = tool.handler(ctx, tool.args_model.model_validate(act.args))
    except (ToolError, ValidationError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        rt.store.set_pending_status(act, "failed")
        log("failed", msg)
        _note(rt, act, f"Пользователь подтвердил действие «{act.summary}», но оно не выполнено: {msg}", f"Не удалось: {msg}", error=True)
        raise Unprocessable(f"Не удалось выполнить действие: {msg}") from e
    except Exception as e:  # noqa: BLE001 — сбой БД и т.п.: действие не должно «зависнуть» подтверждённым
        logger.exception("действие %s (%s) упало", act.id, act.tool_name)
        rt.store.set_pending_status(act, "failed")
        log("failed", f"внутренняя ошибка: {type(e).__name__}")
        _note(rt, act, f"Пользователь подтвердил действие «{act.summary}», но оно не выполнено из-за ошибки сервера.",
              "Не удалось: ошибка сервера. Действие не выполнено.", error=True)
        raise InternalError("Действие не выполнено из-за ошибки сервера. Попробуйте ещё раз.") from e

    log("confirmed", json.dumps(result, ensure_ascii=False, default=str))
    shown = f"Готово: {act.summary}"
    _note(rt, act, f"Пользователь подтвердил действие «{act.summary}». Выполнено. Результат: {json.dumps(result, ensure_ascii=False, default=str)}", shown)
    return {"status": "confirmed", "action_id": act.id, "summary": act.summary, "result": result, "message": shown}


def reject_action(rt: Runtime, principal: Principal, action_id: str) -> dict[str, Any]:
    act = rt.store.get_pending(principal, action_id)
    if act.status != "pending" or not rt.store.claim_pending(act, "rejected"):
        raise Conflict(f"Действие уже обработано (статус: {act.status}).")
    rt.store.log(principal, act.conversation_id, act.tool_name, act.args, "rejected")
    shown = f"Отменено: {act.summary}"
    _note(rt, act, f"Пользователь отклонил действие «{act.summary}». Оно не выполнено.", shown)
    return {"status": "rejected", "action_id": act.id, "message": shown}
