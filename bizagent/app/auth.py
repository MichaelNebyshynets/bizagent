"""Авторизация на базе JWT-токенов."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import os
from datetime import datetime, timedelta, timezone

import jwt

from .context import Principal

# Ключ подписи токенов берётся из окружения (run.py сам кладёт случайный JWT_SECRET в .env).
# Ключ в коде публичного репозитория позволил бы любому выписать себе токен владельца.
SECRET_KEY = os.getenv("JWT_SECRET", "")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

# Токены доступны только при DB_BACKEND=mock.
DEMO_USERS: dict[str, Principal] = {
    "demo-owner-uyut": Principal(user_id=1, company_id=1, role="owner", name="Владелец (Уютный дом)"),
    "demo-manager-uyut": Principal(user_id=2, company_id=1, role="manager", name="Менеджер (Уютный дом)"),
    "demo-accountant-uyut": Principal(user_id=3, company_id=1, role="accountant", name="Бухгалтер (Уютный дом)"),
    "demo-owner-flora": Principal(user_id=4, company_id=2, role="owner", name="Владелец (Флора)"),
}

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = secrets.token_bytes(16) if salt is None else salt
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024**2)
    return f"scrypt:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    # Делаем одинаковую работу для неизвестного email и аккаунта без пароля.
    if not stored:
        hash_password(password, bytes(16))
        return False
    try:
        scheme, salt_hex, digest_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        if scheme != "scrypt" or len(salt) != 16 or len(digest_hex) != 128:
            return False
        return hmac.compare_digest(hash_password(password, salt), stored)
    except (ValueError, UnicodeError):
        return False


def create_access_token(user_id: int, company_id: int, role: str, name: str) -> str:
    """Генерация JWT-токена с данными пользователя."""
    payload = {
        "auth_version": 2,
        "user_id": user_id,
        "company_id": company_id,
        "role": role,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def principal_from_token(token: str | None, *, allow_demo: bool = False) -> Principal | None:
    """Извлечение данных пользователя из токена."""
    if not token:
        return None
    
    if allow_demo and token in DEMO_USERS:
        return DEMO_USERS[token]
    
    if len(SECRET_KEY.encode()) < 32:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp"]})
        if payload.get("auth_version") != 2:
            return None
        return Principal(
            user_id=payload["user_id"],
            company_id=payload["company_id"],
            role=payload["role"],
            name=payload.get("name", "")
        )
    except (jwt.PyJWTError, KeyError):
        return None
