# БизнесПомощник · РБ

Веб-система для малого бизнеса с ИИ-агентом. Бэкенд: `bizagent` (FastAPI). Фронтенд: `biznes-frontend` (React + Vite).
Подробное описание проекта и решений: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## Запуск одной командой

```bash
python3 run.py         # Windows: py run.py
```

Скрипт сам:
1. создаст `.env` из `.env.example` (настройки базы и модели);
2. поднимет Postgres в Docker, при первом запуске создаст таблицы и зальёт демо-данные;
3. проверит Ollama и модель (и запустит Ollama, если она установлена, но не запущена);
4. поставит недостающие зависимости бэкенда и фронтенда;
5. запустит бэкенд и фронтенд в этом же окне и откроет http://localhost:5173.

Остановить: **Ctrl+C**. Postgres остаётся работать в Docker (`docker compose stop`, чтобы остановить).

Вход: `owner@uyut.by`, `manager@uyut.by`, `accountant@uyut.by`, `owner@flora.by`.

| Нужно | Зачем |
|---|---|
| Python 3.10+ | бэкенд |
| Node.js 18+ | фронтенд |
| Docker Desktop (запущенный) | Postgres с pgvector |
| Ollama + `ollama pull qwen2.5:7b` | локальная модель (можно без неё: `LLM_PROVIDER=mock` в `.env`) |

Варианты:
- `python3 run.py --mock` — без Docker и Postgres, данные в памяти (вход только по демо-токену);
- `python3 run.py --no-browser` — не открывать браузер.

Модель, базу и таймауты меняйте в `.env` (не в `.env.example`).
