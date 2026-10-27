"""База знаний (RAG) поверх PostgreSQL."""
from __future__ import annotations
from dataclasses import dataclass
import psycopg2
from psycopg2.extras import RealDictCursor

@dataclass(frozen=True)
class KBChunk:
    title: str
    source_url: str
    doc_date: str
    text: str

class KnowledgeBase:
    def __init__(self, dsn: str = "dbname=bizagent_db user=postgres password=postgres host=localhost port=5432") -> None:
        self.dsn = dsn

    def _get_conn(self):
        return psycopg2.connect(self.dsn)

    def add(self, *, title: str, source_url: str, doc_date: str, text: str) -> None:
        """Добавление документа и его чанков в PostgreSQL."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO kb_documents (title, source_url, doc_date) VALUES (%s, %s, %s) RETURNING id;",
                    (title, source_url, doc_date)
                )
                doc_id = cur.fetchone()[0]
                for part in text.split("\n\n"):
                    part = part.strip()
                    if part:
                        cur.execute(
                            "INSERT INTO kb_chunks (document_id, content) VALUES (%s, %s);",
                            (doc_id, part)
                        )
                conn.commit()

    def search(self, query: str, limit: int = 3) -> list[KBChunk]:
        """Ищем в базе данных по ключевым словам из запроса пользователя."""
        words = [w.strip() for w in query.split() if len(w) > 2]
        if not words:
            return []

        # Формируем SQL-запрос с поиском по любому из слов
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Ищем чанки, где встречаются слова из запроса
                sql = """
                    SELECT d.title, d.source_url, d.doc_date::text, c.content
                    FROM kb_chunks c
                    JOIN kb_documents d ON c.document_id = d.id
                    WHERE 
                """
                conditions = []
                params = []
                for w in words:
                    conditions.append("c.content ILIKE %s OR d.title ILIKE %s")
                    params.extend([f"%{w}%", f"%{w}%"])
                
                sql += " OR ".join(conditions) + " LIMIT %s;"
                params.append(limit)

                cur.execute(sql, tuple(params))
                rows = cur.fetchall()

                return [
                    KBChunk(
                        title=r['title'],
                        source_url=r['source_url'],
                        doc_date=r['doc_date'],
                        text=r['content']
                    ) for r in rows
                ]

# ------------------------------------------------------------------ без Postgres (тесты и DB_BACKEND=mock)

import re as _re


def _stems(text: str) -> set[str]:
    # Очень грубая «лемматизация» по первым 5 буквам: достаточно для заглушки
    return {w[:5] for w in _re.findall(r"\w+", text.lower()) if len(w) >= 3}


class InMemoryKnowledgeBase:
    """Та же база знаний (интерфейс add/search), но в памяти. Нужна для тестов и режима DB_BACKEND=mock."""

    def __init__(self) -> None:
        self._chunks: list[KBChunk] = []

    def add(self, *, title: str, source_url: str, doc_date: str, text: str) -> None:
        for part in _re.split(r"\n\s*\n", text):
            part = part.strip()
            if part:
                self._chunks.append(KBChunk(title, source_url, doc_date, part))

    def search(self, query: str, limit: int = 3) -> list[KBChunk]:
        q = _stems(query)
        scored = [(len(q & _stems(c.text + " " + c.title)), c) for c in self._chunks]
        scored = [(s, c) for s, c in scored if s > 0]
        scored.sort(key=lambda sc: sc[0], reverse=True)
        return [c for _, c in scored[:limit]]
