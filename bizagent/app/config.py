from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # mock — заглушка без ИИ (для разработки и демо), openai_compat — любая модель с OpenAI-совместимым API
    llm_provider: str = "mock"
    llm_base_url: str = "http://localhost:11434/v1"  # пример: Ollama; для vLLM обычно http://host:8000/v1
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_s: float = 60.0
    # Защита от зацикливания: сколько раз за один запрос агент может обратиться к модели
    max_steps: int = 6
    # Сколько минут у пользователя есть на подтверждение действия
    confirm_ttl_min: int = 15
    # Где хранить файлы, которые пользователи прикладывают к чату
    upload_dir: str = "uploaded_files"
    # postgres — настоящая БД (по умолчанию); mock — данные в памяти, без Postgres (тесты, демо без Docker)
    db_backend: str = "postgres"
    database_url: str = "dbname=bizagent_db user=postgres password=postgres host=localhost port=5432"

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", d.llm_provider),
            llm_base_url=os.getenv("LLM_BASE_URL", d.llm_base_url),
            llm_api_key=os.getenv("LLM_API_KEY", d.llm_api_key),
            llm_model=os.getenv("LLM_MODEL", d.llm_model),
            llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", d.llm_timeout_s)),
            max_steps=int(os.getenv("MAX_STEPS", d.max_steps)),
            confirm_ttl_min=int(os.getenv("CONFIRM_TTL_MIN", d.confirm_ttl_min)),
            upload_dir=os.getenv("UPLOAD_DIR", d.upload_dir),
            db_backend=os.getenv("DB_BACKEND", d.db_backend),
            database_url=os.getenv("DATABASE_URL", d.database_url),
        )
