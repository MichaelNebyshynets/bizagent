"""Время. Вынесено отдельно, чтобы в тестах его можно было подменить
(например, проверить, что подтверждение действия истекает через 15 минут)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

# В Беларуси постоянное время UTC+3 без перехода на летнее, поэтому фиксированного смещения достаточно
# (и не нужен пакет tzdata на Windows).
MINSK = timezone(timedelta(hours=3))

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(MINSK)
