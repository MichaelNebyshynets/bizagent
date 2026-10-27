# BizAgent: каркас ИИ-агента для МСБ РБ

Ядро агента для веб-системы поддержки малого бизнеса: цикл с tool calling, роли, подтверждение
действий, аудит, изоляция компаний, моковые данные. Работает **без настоящей модели** (заглушка),
а настоящую подключаешь конфигом.

## Быстрый старт

Проще всего запускать весь проект из корня репозитория: `python run.py` (поднимет Postgres, бэкенд и фронтенд).

Только бэкенд, вручную (Python 3.10+):

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest -v                                         # все тесты; Postgres не нужен (режим mock)
DB_BACKEND=mock uvicorn app.main:app --reload     # без Postgres; API на http://localhost:8000, документация: /docs
```

Демо-пользователи (токен передаётся как `Authorization: Bearer <токен>`):

| Токен | Компания | Роль |
|---|---|---|
| `demo-owner-uyut` | Уютный дом | владелец |
| `demo-manager-uyut` | Уютный дом | менеджер |
| `demo-accountant-uyut` | Уютный дом | бухгалтер |
| `demo-owner-flora` | Флора | владелец (вторая компания, для проверки изоляции) |

```bash
curl -s localhost:8000/agent/chat -H "Authorization: Bearer demo-owner-uyut" \
  -H "Content-Type: application/json" -d '{"message":"какие товары заканчиваются?"}'
```

## Подключение настоящей модели

Любой сервер с OpenAI-совместимым API (vLLM, Ollama, LM Studio, облачные):

```bash
export LLM_PROVIDER=openai_compat                 # PowerShell: $env:LLM_PROVIDER="openai_compat"
export LLM_BASE_URL=http://localhost:11434/v1     # пример для Ollama
export LLM_MODEL=<имя модели с поддержкой tool calling>
export LLM_API_KEY=<если нужен>
```

Не каждая модель надёжно вызывает инструменты. Проверяй именно это на наборе тестовых вопросов.

## Структура

```
app/
  main.py            HTTP: /agent/chat, /agent/chat/stream (SSE), confirm/reject, audit
  auth.py            ЗАГЛУШКА авторизации (заменить на JWT)
  mock_data.py       моковая БД + генератор данных (интерфейс = будущий слой над PostgreSQL)
  kb.py              ЗАГЛУШКА базы знаний (заменить на pgvector); по умолчанию пустая
  llm/               LLMProvider (интерфейс), openai_compat (настоящая), mock (заглушки)
  agent/
    loop.py          цикл агента (главный файл)
    tools.py         инструменты: аргументы (Pydantic), права, подтверждение
    actions.py       подтверждение/отклонение действий
    store.py         диалоги, ожидающие действия, аудит
    prompts.py       системный промпт
tests/
  test_core.py       34 теста ядра (без FastAPI и без настоящей модели)
  test_api.py        тесты HTTP-слоя
```

## Что здесь заглушка

| Заглушка | На что заменить |
|---|---|
| `auth.py` (демо-токены) | разбор JWT; `company_id`, `user_id`, `role` только из токена |
| `mock_data.py` | SQLAlchemy/asyncpg над PostgreSQL; `company_id` в каждом запросе, лучше ещё и Row Level Security |
| `store.py` (память) | таблицы `agent_conversations`, `agent_messages`, `agent_pending_actions`, `agent_tool_calls` |
| `kb.py` (поиск по словам, пустая) | pgvector + реальные документы (НК, акты МНС, pravo.by) с датой и ссылкой |
| `MockLLM` | настоящая модель |

## Что ещё не сделано

- Потоковый вывод **текста по токенам** (сейчас SSE шлёт события шагов агента).
- Обрезка длинной истории диалога под контекст модели.
- Блокирующие вызовы БД: в `execute_call` отмечено место (`TODO(БД)`), где нужен `await` или `run_in_threadpool`.
- Набор оценочных вопросов (30-50 штук с эталонами) для метрик на защите.

## Запуск без Postgres (режим mock)

По умолчанию бэкенд работает с PostgreSQL (`DB_BACKEND=postgres`, строка подключения в `DATABASE_URL`).
Для тестов и демо без Docker есть режим с данными в памяти:

```bash
DB_BACKEND=mock uvicorn app.main:app --reload    # Windows PowerShell: $env:DB_BACKEND="mock"; uvicorn app.main:app --reload
```

В режиме mock вход по email (`/auth/login`) недоступен (ответ 503), используйте демо-токены. База знаний в этом режиме пустая.
Все тесты (`pytest -v`) работают в режиме mock и Postgres не требуют.

## Загрузка файлов в чат

Поддерживаются `.txt .md .csv` (UTF-8 или Windows-1251, как в выгрузках 1С), `.xlsx`, `.docx`, `.pdf` (только с текстовым слоем). До 10 МБ.

1. `POST /agent/upload` (multipart: `file`, `category`) → `{"file_id": "...", "filename": "...", "chars": ..., ...}`.
2. `POST /agent/chat` с `"file_ids": ["<file_id>"]` (до 5 файлов) — файл приложен к этому сообщению.
3. Агент читает файл инструментом `read_uploaded_file` кусками по 4000 символов. Текст файла не вставляется в промпт целиком.

Ещё: `GET /agent/files` (свои файлы), `DELETE /agent/files/{file_id}`.

Безопасность: файл видит только загрузивший его пользователь в своей компании (чужой `file_id` = 404).
Имя файла от пользователя не используется как путь на диске. Файлы лежат в `UPLOAD_DIR` (по умолчанию `uploaded_files/<company_id>/<user_id>/<file_id>/`).
Содержимое файла для агента это данные, а не инструкции. Любая запись данных по-прежнему только через подтверждение пользователя.

## История чатов

У каждого пользователя свой список чатов, чужие чаты не видны (404). «Новый чат» не удаляет старые.

| Запрос | Что делает |
|---|---|
| `GET /agent/conversations` | чаты пользователя, новые сверху: `id`, `title` (первый вопрос), `created_at`, `updated_at` |
| `GET /agent/conversations/{id}` | чат как его видит пользователь: вопросы, ответы, `trace`, карточки подтверждения с текущим `status` |
| `DELETE /agent/conversations/{id}` | удалить чат (аудит при этом сохраняется) |

Где хранится:
- `DB_BACKEND=postgres` — `app/agent/pg_store.py`, таблицы `agent_conversations`, `agent_messages`, `agent_pending_actions`, `agent_tool_calls`. История переживает перезапуск. Недостающие колонки (`title`, `updated_at`, `kind`) бэкенд добавляет сам при первом запросе.
- `DB_BACKEND=mock` — `app/agent/store.py`, в памяти (пропадает при перезапуске).

Подтверждение действия в Postgres атомарное (`UPDATE ... WHERE status='pending'`): двойной клик или два сервера не выполнят действие дважды.

Тесты истории на настоящем Postgres (БАЗА БУДЕТ ОЧИЩЕНА, указывайте отдельную тестовую):

```bash
BIZAGENT_TEST_PG="dbname=bizagent_test user=postgres password=postgres host=localhost" pytest tests/test_history.py -v
```
