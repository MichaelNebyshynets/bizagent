"""Windows console launcher. Keep this window open while using BizAgent."""
import ctypes
import contextlib
import hashlib
import json
import msvcrt
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ["LOCALAPPDATA"]) / "BizAgent" / "data"
API = "http://127.0.0.1:18420"
OLLAMA = "http://127.0.0.1:18421"
PG = ROOT / "pgsql" / "bin"
MODEL = "qwen2.5:7b"
DIGEST = "eaae7d713d221caca1b958e11972bcaca9a06b06faa830e8de168d8de831ffa7"
URL = "https://github.com/ollama/ollama/releases/download/v0.12.11/ollama-windows-amd64.zip"


def runtime():
    target = DATA / "ollama-0.12.11"
    if (target / "ollama.exe").is_file():
        return target / "ollama.exe"
    if shutil.disk_usage(DATA).free < 13 * 1024**3:
        raise RuntimeError("Для первой загрузки освободите 13 ГиБ.")
    archive = DATA / "ollama.download"
    for attempt in range(3):
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(URL, timeout=90) as response, archive.open("wb") as out:
                total = 0
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
                    digest.update(chunk)
                    total += 1
                    if total % 16 == 0:
                        print(f"Загрузка Ollama: {total} МиБ", flush=True)
            if digest.hexdigest() != DIGEST:
                raise ValueError("Не совпала контрольная сумма Ollama.")
            break
        except (OSError, ValueError) as exc:
            print(exc)
            if attempt == 2:
                raise
            time.sleep(3)
    temporary = DATA / "ollama-unpacking"
    with zipfile.ZipFile(archive) as package:
        package.extractall(temporary)
    if not (temporary / "ollama.exe").is_file():
        raise RuntimeError("В архиве отсутствует ollama.exe.")
    temporary.rename(target)
    archive.unlink()
    return target / "ollama.exe"


def wait_http(url, process):
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError("Сервис завершился. Подробности в журнале.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.load(response)
        except OSError:
            time.sleep(1)
    raise TimeoutError(url)


def stop_child(process):
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=30)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / "running.lock").open("a+b") as lock, contextlib.ExitStack() as cleanup:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("БизнесПомощник уже запущен.")
            if (DATA / "ready").exists():
                webbrowser.open(API)
            return
        ready = DATA / "ready"
        ready.unlink(missing_ok=True)
        for port in (18420, 18421, 18422):
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    raise RuntimeError(f"Порт {port} занят. Закройте приложение, которое его использует.")
        print("Первый запуск требует интернета. Для модели рекомендуется 16 ГБ памяти.")
        exe = runtime()
        config = DATA / "settings.json"
        if not config.exists():
            temporary = config.with_suffix(".tmp")
            temporary.write_text(json.dumps({k: secrets.token_urlsafe(32) for k in ("db", "jwt")}))
            temporary.replace(config)
        keys = json.loads(config.read_text())
        os.environ.update(DATABASE_URL=f"host=127.0.0.1 port=18422 user=bizagent password={keys['db']} dbname=postgres",
                          JWT_SECRET=keys["jwt"], DB_BACKEND="postgres", LLM_PROVIDER="openai_compat",
                          LLM_MODEL=MODEL, LLM_BASE_URL=OLLAMA + "/v1", LLM_TIMEOUT_S="240",
                          UPLOAD_DIR=str(DATA / "uploads"), OLLAMA_HOST="127.0.0.1:18421",
                          OLLAMA_MODELS=str(DATA / "models"), PYTHONUTF8="1")
        log = cleanup.enter_context((DATA / "services.log").open("ab"))
        def run(args, **kwargs):
            subprocess.run(args, cwd=ROOT / "bizagent", check=True, **kwargs)
        def short(path):
            buffer = ctypes.create_unicode_buffer(32768)
            if not ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer)):
                raise ctypes.WinError()
            return Path(buffer.value)
        pg = short(PG)
        db = short(DATA) / "postgres"
        if not (db / "PG_VERSION").exists():
            pw = DATA / "init-password.tmp"
            pw.write_text(keys["db"], encoding="ascii")
            try:
                run([pg / "initdb.exe", "-D", db, "-L", short(ROOT / "pgsql" / "share"), "-U", "bizagent", "-A", "scram-sha-256", "-E", "UTF8", "--locale=C", "--pwfile", short(pw)])
            finally:
                pw.unlink(missing_ok=True)
        ctl = [pg / "pg_ctl.exe", "-D", db]
        run(ctl + ["-o", "-h 127.0.0.1 -p 18422", "-l", short(DATA) / "postgres.log", "-w", "start"])
        cleanup.callback(run, ctl + ["-m", "fast", "-w", "stop"])
        run([sys.executable, "db_init.py", "--schema", ROOT / "schema.sql"])
        import psycopg2
        from app.auth import hash_password
        with contextlib.closing(psycopg2.connect(os.environ["DATABASE_URL"])) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email=%s AND password_hash IS NULL", ("owner@uyut.by",))
            row = cur.fetchone()
            if row:
                import getpass
                while True:
                    password = getpass.getpass("Задайте пароль для owner@uyut.by (12–128 символов): ")
                    if 12 <= len(password) <= 128 and password == getpass.getpass("Повторите пароль: "):
                        break
                cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hash_password(password), row[0]))
        ollama = subprocess.Popen([exe, "serve"], stdout=log, stderr=log)
        cleanup.callback(stop_child, ollama)
        models = wait_http(OLLAMA + "/api/tags", ollama)
        if MODEL not in {item["name"] for item in models["models"]}:
            run([exe, "pull", MODEL])
        api = subprocess.Popen([sys.executable, "-m", "uvicorn", "desktop_server:app", "--host", "127.0.0.1", "--port", "18420"],
                               cwd=ROOT / "bizagent", stdout=log, stderr=log)
        cleanup.callback(stop_child, api)
        wait_http(API + "/health", api)
        ready.touch()
        cleanup.callback(ready.unlink, missing_ok=True)
        webbrowser.open(API)
        input("Программа открыта в браузере. Для остановки нажмите Enter.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Ошибка: {exc}\nЖурналы: {DATA}")
        input("Нажмите Enter для выхода.")
        sys.exit(1)

