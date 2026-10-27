"""Скрипт автоматического чтения .txt файлов из папки kb_docs и загрузки в базу знаний PostgreSQL."""
from __future__ import annotations
import os
import psycopg2

DB_CONFIG = {
    "dbname": "bizagent_db",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

DOCS_DIR = "kb_docs"

def parse_kb_file(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    parts = content.split("---")
    header = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""
    
    meta = {}
    for line in header.split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip().lower()] = val.strip()
            
    return {
        "title": meta.get("title", "Без названия"),
        "source_url": meta.get("source_url", "https://pravo.by"),
        "doc_date": meta.get("doc_date", "2026-01-01"),
        "text": body
    }

def seed_files():
    if not os.path.exists(DOCS_DIR):
        print(f"Папка {DOCS_DIR} не найдена!")
        return

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    print("Чтение файлов базы знаний из папки...")
    for filename in os.listdir(DOCS_DIR):
        if filename.endswith(".txt"):
            filepath = os.path.join(DOCS_DIR, filename)
            doc = parse_kb_file(filepath)
            
            # Проверяем, нет ли уже такого документа
            cur.execute("SELECT id FROM kb_documents WHERE title = %s;", (doc["title"],))
            if cur.fetchone():
                print(f"Документ уже существует: {doc['title']}")
                continue
                
            cur.execute(
                "INSERT INTO kb_documents (title, source_url, doc_date) VALUES (%s, %s, %s) RETURNING id;",
                (doc["title"], doc["source_url"], doc["doc_date"])
            )
            doc_id = cur.fetchone()[0]
            
            # Разбиваем текст на абзацы (чанки)
            chunks = [c.strip() for c in doc["text"].split("\n\n") if c.strip()]
            for chunk in chunks:
                cur.execute(
                    "INSERT INTO kb_chunks (document_id, content) VALUES (%s, %s);",
                    (doc_id, chunk)
                )
            print(f"Загружен документ: {doc['title']} (чанков: {len(chunks)})")
            
    conn.commit()
    cur.close()
    conn.close()
    print("База знаний из файлов успешно синхронизирована с БД!")

if __name__ == "__main__":
    seed_files()