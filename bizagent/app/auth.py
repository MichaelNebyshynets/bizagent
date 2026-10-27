"""Авторизация на базе JWT-токенов."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import jwt

from .context import Principal

# Ключ подписи токенов берётся из окружения (run.py сам кладёт случайный JWT_SECRET в .env).
# Ключ в коде публичного репозитория позволил бы любому выписать себе токен владельца.
SECRET_KEY = os.getenv("JWT_SECRET", "")
if not SECRET_KEY:
    SECRET_KEY = "dev-only-insecure-key"
    logging.getLogger("auth").warning("JWT_SECRET не задан: используется небезопасный ключ для разработки")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

# Демо-пользователи для совместимости
DEMO_USERS: dict[str, Principal] = {
    "demo-owner-uyut": Principal(user_id=1, company_id=1, role="owner", name="Владелец (Уютный дом)"),
    "demo-manager-uyut": Principal(user_id=2, company_id=1, role="manager", name="Менеджер (Уютный дом)"),
    "demo-accountant-uyut": Principal(user_id=3, company_id=1, role="accountant", name="Бухгалтер (Уютный дом)"),
    "demo-owner-flora": Principal(user_id=4, company_id=2, role="owner", name="Владелец (Флора)"),
}

def create_access_token(user_id: int, company_id: int, role: str, name: str) -> str:
    """Генерация JWT-токена с данными пользователя."""
    payload = {
        "user_id": user_id,
        "company_id": company_id,
        "role": role,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def principal_from_token(token: str | None) -> Principal | None:
    """Извлечение данных пользователя из токена."""
    if not token:
        return None
    
    if token in DEMO_USERS:
        return DEMO_USERS[token]
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return Principal(
            user_id=payload["user_id"],
            company_id=payload["company_id"],
            role=payload["role"],
            name=payload.get("name", "")
        )
    except (jwt.PyJWTError, KeyError):
        return None