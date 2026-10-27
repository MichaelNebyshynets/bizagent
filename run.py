#!/usr/bin/env python3
"""Запуск всего проекта одной командой:

    python run.py            # Postgres (Docker) + Ollama + бэкенд + фронтенд
    python run.py --mock     # без Docker и Postgres: данные в памяти (для быстрой проверки)

Что делает по порядку:
  1. Читает настройки из .env в корне проекта (если его нет — создаёт из .env.example).
  2. Postgres: `docker compose up -d postgres`, затем db_init.py (таблицы, демо-данные, счётчики id).
  3. Модель: если LLM_PROVIDER=openai_compat и это Ollama — проверяет, что она запущена и модель скачана.
  4. Ставит недостающие зависимости: бэкенд (.venv + requirements.txt) и фронтенд (npm install).
  5. Запускает бэкенд (uvicorn, порт 8000) и фронтенд (vite, порт 5173) в этом окне и открывает браузер.
Ctrl+C останавливает бэкенд и фронтенд. Postgres остаётся работать в Docker (остановить: docker compose stop).

Нужны: Python 3.10+, Node.js 18+, Docker Desktop (кроме режима --mock), Ollama (если используете локальную модель).
Только стандартная библиотека Python: скрипт работает до установки зависимостей.
"""
from __future__ import annotations

import argparse
import json
import secrets
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "bizagent"
FRONTEND = ROOT / "biznes-frontend"
SCHEMA = ROOT / "schema.sql"
ENV_FILE, ENV_EXAMPLE = ROOT / ".env", ROOT / ".env.example"
IS_WIN = os.name == "nt"
BACKEND_PORT, FRONTEND_PORT = 8000, 5173
BACKEND_IMPORTS = "fastapi, uvicorn, multipart, jwt, psycopg2, openpyxl, docx, pypdf, httpx"

USE_COLOR = sys.stdout.isatty() and not IS_WIN or os.getenv("WT_SESSION")
C = {"run": "36", "ok": "32", "warn": "33", "err": "31", "backend": "35", "frontend": "34", "ollama": "90"}


def paint(text: str, kind: str) -> str:
    return f"\033[{C[kind]}m{text}\033[0m" if USE_COLOR else text


def say(msg: str, kind: str = "run") -> None:
    mark = {"run": "▸", "ok": "✓", "warn": "!", "err": "✗"}[kind]
    print(paint(f"{mark} {msg}", kind), flush=True)


def fail(msg: str, hint: str = "") -> None:
    say(msg, "err")
    if hint:
        print("  " + hint.replace("\n", "\n  "))
    sys.exit(1)


# ------------------------------------------------------------------ настройки


def load_env() -> dict[str, str]:
    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        say(f"Создал .env из .env.example — настройки модели и базы правьте в нём", "warn")
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    if not env.get("JWT_SECRET"):
        # Свой случайный ключ подписи токенов входа на каждой машине: в репозитории его нет
        env["JWT_SECRET"] = secrets.token_urlsafe(32)
        text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
        lines = [l for l in text.splitlines() if not l.strip().startswith("JWT_SECRET=")]
        lines.append(f"JWT_SECRET={env['JWT_SECRET']}")
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        say("Сгенерировал JWT_SECRET в .env", "ok")
    return env


# ------------------------------------------------------------------ утилиты


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def wait_port(port: int, timeout: float, proc: subprocess.Popen | None = None) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port):
            return True
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(0.3)
    return False


def http_json(url: str, timeout: float = 2.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def run(cmd: list[str], cwd: Path, env: dict | None = None, quiet: bool = False) -> int:
    out = subprocess.DEVNULL if quiet else None
    return subprocess.run(cmd, cwd=cwd, env=env, stdout=out, stderr=out).returncode


def venv_python() -> Path:
    return BACKEND / ".venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")


# ------------------------------------------------------------------ шаги


def check_layout() -> None:
    for p, what in ((BACKEND / "app" / "main.py", "бэкенд"), (FRONTEND / "package.json", "фронтенд")):
        if not p.exists():
            fail(f"Не нашёл {what}: {p}", "run.py должен лежать в корне проекта, рядом с папками bizagent и biznes-frontend.")


def ensure_backend_deps() -> Path:
    py = venv_python()
    if not py.exists():
        say("Создаю виртуальное окружение бэкенда (.venv)…")
        if run([sys.executable, "-m", "venv", ".venv"], BACKEND) != 0:
            fail("Не удалось создать .venv")
    if run([str(py), "-c", f"import {BACKEND_IMPORTS}"], BACKEND, quiet=True) != 0:
        say("Ставлю зависимости бэкенда (pip install -r requirements.txt)…")
        if run([str(py), "-m", "pip", "install", "-q", "-r", "requirements.txt"], BACKEND) != 0:
            fail("pip install не удался", "Посмотрите ошибку выше. Частая причина: нет интернета или слишком новая версия Python.")
    say("Зависимости бэкенда на месте", "ok")
    return py


def ensure_frontend_deps() -> str:
    npm = shutil.which("npm")
    if not npm:
        fail("Не найден npm", "Установите Node.js 18+ с https://nodejs.org")
    marker = FRONTEND / "node_modules" / ".package-lock.json"
    if not marker.exists() or marker.stat().st_mtime < (FRONTEND / "package.json").stat().st_mtime:
        say("Ставлю зависимости фронтенда (npm install)…")
        if run([npm, "install", "--no-audit", "--no-fund"], FRONTEND) != 0:
            fail("npm install не удался", "Посмотрите ошибку выше.")
    say("Зависимости фронтенда на месте", "ok")
    return npm


def docker_compose_cmd() -> list[str] | None:
    docker = shutil.which("docker")
    if docker and run([docker, "compose", "version"], ROOT, quiet=True) == 0:
        return [docker, "compose"]
    legacy = shutil.which("docker-compose")
    return [legacy] if legacy else None


def ensure_postgres(py: Path, env: dict) -> None:
    if port_open(5432):
        say("Postgres уже запущен на порту 5432", "ok")
    else:
        compose = docker_compose_cmd()
        if compose is None:
            fail("Postgres не запущен, а Docker не найден",
                 "Установите и запустите Docker Desktop, либо запустите без базы: python run.py --mock")
        say("Запускаю Postgres в Docker (docker compose up -d postgres)…")
        if run(compose + ["up", "-d", "postgres"], ROOT) != 0:
            fail("docker compose не смог запустить Postgres", "Проверьте, что Docker Desktop запущен (иконка кита в трее/строке меню).")
        if not wait_port(5432, 60):
            fail("Postgres не открыл порт 5432 за минуту", "Посмотрите логи: docker compose logs postgres")
    if run([str(py), "db_init.py", "--schema", str(SCHEMA)], BACKEND, env=env) != 0:
        fail("Не удалось подготовить базу (db_init.py)")


def ensure_ollama(env: dict, procs: list) -> None:
    if env.get("LLM_PROVIDER", "mock") != "openai_compat":
        say(f"Модель: демо-заглушка без ИИ (LLM_PROVIDER={env.get('LLM_PROVIDER', 'mock')})", "warn")
        return
    base = env.get("LLM_BASE_URL", "")
    model = env.get("LLM_MODEL", "")
    if ":11434" not in base:  # не Ollama (vLLM, облако) — проверять нечего
        say(f"Модель: {model} на {base}", "ok")
        return
    api = base.rsplit("/v1", 1)[0]
    tags_url = f"{api}/api/tags"

    def tags():
        try:
            return [m["name"] for m in http_json(tags_url)["models"]]
        except (urllib.error.URLError, OSError, KeyError, ValueError):
            return None

    names = tags()
    if names is None:
        ollama = shutil.which("ollama")
        if not ollama:
            say(f"Ollama не отвечает на {api} и не найдена в PATH. Агент будет отвечать ошибкой, пока её не запустите.", "warn")
            return
        say("Ollama не запущена: запускаю ollama serve…")
        p = subprocess.Popen([ollama, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **_group_kwargs())
        procs.append(("ollama", p))
        for _ in range(30):
            time.sleep(0.5)
            names = tags()
            if names is not None:
                break
        if names is None:
            say("Ollama так и не ответила. Запустите приложение Ollama вручную.", "warn")
            return
    if model not in names and f"{model}:latest" not in names:
        say(f"Модель {model} не скачана в Ollama. Выполните: ollama pull {model}", "warn")
        if names:
            print("  Есть: " + ", ".join(names))
        return
    say(f"Модель: {model} в Ollama", "ok")


# ------------------------------------------------------------------ процессы


def _group_kwargs() -> dict:
    # Отдельная группа процессов: по Ctrl+C гасим процесс вместе с его детьми (uvicorn --reload, vite)
    return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WIN else {"start_new_session": True}


def start(name: str, cmd: list[str], cwd: Path, env: dict) -> subprocess.Popen:
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1, **_group_kwargs())
    prefix = paint(f"[{name}]".ljust(11), name)

    def pump():
        for line in p.stdout:
            print(f"{prefix}{line.rstrip()}", flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return p


def stop(procs: list) -> None:
    for name, p in reversed(procs):
        if p.poll() is not None:
            continue
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.killpg(p.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    deadline = time.time() + 5
    for _, p in procs:
        try:
            p.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            if not IS_WIN:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except OSError:
                    pass


def _install_signal_handlers() -> None:
    # Ctrl+C работает, даже если запуск унаследовал «игнорировать SIGINT» (например, из фонового задания).
    signal.signal(signal.SIGINT, signal.default_int_handler)

    # Закрыли окно терминала или процесс попросили завершиться: тоже аккуратно гасим бэкенд и фронтенд,
    # иначе они остались бы работать в фоне и держать порты 8000 и 5173.
    def _stop(signum, frame):
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _stop)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _install_signal_handlers()
    ap = argparse.ArgumentParser(description="Запуск БизнесПомощника одной командой")
    ap.add_argument("--mock", action="store_true", help="без Docker и Postgres: данные в памяти")
    ap.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    args = ap.parse_args()

    check_layout()
    file_env = load_env()
    env = {**os.environ, **file_env, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    if args.mock:
        env["DB_BACKEND"] = "mock"
    env.setdefault("DB_BACKEND", "postgres")

    for port, what in ((BACKEND_PORT, "бэкенд"), (FRONTEND_PORT, "фронтенд")):
        if port_open(port):
            fail(f"Порт {port} уже занят (нужен для: {what})", "Скорее всего, проект уже запущен в другом окне. Закройте его или освободите порт.")

    py = ensure_backend_deps()
    npm = ensure_frontend_deps()
    if env["DB_BACKEND"] == "postgres":
        ensure_postgres(py, env)
    else:
        say("База: данные в памяти (--mock), вход по email недоступен, используйте демо-токен", "warn")

    procs: list[tuple[str, subprocess.Popen]] = []
    try:
        ensure_ollama(env, procs)

        say("Запускаю бэкенд…")
        backend = start("backend", [str(py), "-m", "uvicorn", "app.main:app", "--reload", "--port", str(BACKEND_PORT)], BACKEND, env)
        procs.append(("backend", backend))
        if not wait_port(BACKEND_PORT, 60, backend):
            fail("Бэкенд не запустился", "Ошибка выше, в строках [backend].")

        say("Запускаю фронтенд…")
        frontend = start("frontend", [npm, "run", "dev", "--", "--port", str(FRONTEND_PORT), "--strictPort"], FRONTEND, env)
        procs.append(("frontend", frontend))
        if not wait_port(FRONTEND_PORT, 60, frontend):
            fail("Фронтенд не запустился", "Ошибка выше, в строках [frontend].")

        url = f"http://localhost:{FRONTEND_PORT}"
        print()
        say(f"Всё запущено: {url}", "ok")
        print(f"  API и документация: http://localhost:{BACKEND_PORT}/docs")
        if env["DB_BACKEND"] == "postgres":
            print("  Вход: owner@uyut.by, manager@uyut.by, accountant@uyut.by, owner@flora.by")
        print("  Остановить: Ctrl+C\n", flush=True)
        if not args.no_browser:
            webbrowser.open(url)

        while True:
            for name, p in procs:
                if p.poll() is not None:
                    fail(f"Процесс {name} завершился (код {p.returncode})", f"Причина выше, в строках [{name}].")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        say("Останавливаю…")
    finally:
        stop(procs)
    tail = " Postgres продолжает работать (остановить: docker compose stop)" if env["DB_BACKEND"] == "postgres" else ""
    say("Остановлено." + tail, "ok")


if __name__ == "__main__":
    main()
