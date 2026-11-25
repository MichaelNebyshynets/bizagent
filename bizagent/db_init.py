"""Подготовка базы перед запуском (вызывается из run.py, можно и вручную):

    python db_init.py --schema ../../schema.sql

1. Ждёт, пока Postgres начнёт принимать подключения (после `docker compose up` это пара секунд).
2. Если таблиц нет — создаёт их из schema.sql.
3. Если нет компаний — заливает демо-данные (seed_db.py); если база знаний пустая — документы (seed_kb.py).
4. Сдвигает счётчики id до максимального значения. Это чинит базы, залитые старой версией seed_db.py:
   там создание клиента/заказа/расхода через агента падало на дубликате ключа.

Всё идемпотентно: повторный запуск ничего не ломает и не дублирует.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg2

from app.config import Settings

SERIAL_TABLES = ("companies", "users", "products", "clients", "orders", "expenses", "kb_documents", "kb_chunks")


def connect(dsn: str, wait_s: int):
    deadline = time.time() + wait_s
    while True:
        try:
            return psycopg2.connect(dsn)
        except psycopg2.OperationalError as e:
            if time.time() > deadline:
                print(f"Postgres недоступен: {str(e).strip()}")
                sys.exit(1)
            time.sleep(1)


def count(cur, table: str) -> int:
    cur.execute(f"SELECT count(*) FROM {table}")
    return cur.fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schema", required=True, help="путь к schema.sql")
    ap.add_argument("--wait", type=int, default=60, help="сколько секунд ждать Postgres")
    a = ap.parse_args()

    conn = connect(Settings.from_env().database_url, a.wait)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT to_regclass('public.companies')")
    if cur.fetchone()[0] is None:
        print("Таблиц нет: создаю из schema.sql…")
        try:
            cur.execute(Path(a.schema).read_text(encoding="utf-8"))
        except psycopg2.Error as e:
            print(f"Не удалось применить schema.sql: {str(e).strip()}")
            if "vector" in str(e):
                print("Нужен Postgres с расширением pgvector: используйте docker compose из проекта (образ ankane/pgvector).")
            sys.exit(1)

    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS external_sale_id VARCHAR(100)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_imports (
            id BIGSERIAL PRIMARY KEY,
            company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id INT NOT NULL,
            author TEXT NOT NULL,
            filename VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            orders INT NOT NULL,
            rows INT NOT NULL,
            duplicates INT NOT NULL,
            revenue NUMERIC(24, 2) NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sales_imports_company_id ON sales_imports (company_id, id DESC);
    """)

    cur.execute("""
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS sales_import_id BIGINT REFERENCES sales_imports(id);
        CREATE INDEX IF NOT EXISTS idx_orders_company_import ON orders (company_id, sales_import_id)
            WHERE sales_import_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_orders_company_date ON orders (company_id, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items (order_id);
    """)

    cur.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INT NOT NULL DEFAULT 0;
        ALTER TABLE sales_imports ADD COLUMN IF NOT EXISTS reversed_at TIMESTAMPTZ;
        ALTER TABLE sales_imports ADD COLUMN IF NOT EXISTS reversed_by INT;
        ALTER TABLE sales_imports ADD COLUMN IF NOT EXISTS reversed_by_name TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_active_orders_company_external_sale
            ON orders (company_id, external_sale_id) WHERE external_sale_id IS NOT NULL AND status = 'completed';
        DROP INDEX IF EXISTS uq_orders_company_external_sale;

        CREATE TABLE IF NOT EXISTS purchase_orders (
            id BIGSERIAL PRIMARY KEY,
            company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id INT NOT NULL,
            author TEXT NOT NULL,
            supplier VARCHAR(255) NOT NULL,
            request_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (company_id, request_id)
        );
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_company ON purchase_orders (company_id, id DESC);
        CREATE TABLE IF NOT EXISTS purchase_order_items (
            purchase_order_id BIGINT NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
            product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            product_name VARCHAR(255) NOT NULL,
            sku VARCHAR(100) NOT NULL,
            quantity INT NOT NULL CHECK (quantity > 0),
            PRIMARY KEY (purchase_order_id, product_id)
        );
    """)

    if os.getenv("SEED_DEMO_DATA", "1") == "1" and count(cur, "companies") == 0:
        print("База пустая: заливаю демо-данные (seed_db.py)…")
        subprocess.run([sys.executable, "seed_db.py"], check=True)
    if count(cur, "kb_documents") == 0 and Path("kb_docs").is_dir():
        print("База знаний пустая: загружаю документы (seed_kb.py)…")
        subprocess.run([sys.executable, "seed_kb.py"], check=True, stdout=subprocess.DEVNULL)

    for t in SERIAL_TABLES:
        # пустая таблица: следующий id = 1; иначе: следующий id = MAX(id) + 1
        cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {t}")

    print(f"База готова: компаний {count(cur, 'companies')}, клиентов {count(cur, 'clients')}, документов в базе знаний {count(cur, 'kb_documents')}.")
    conn.close()


if __name__ == "__main__":
    main()
