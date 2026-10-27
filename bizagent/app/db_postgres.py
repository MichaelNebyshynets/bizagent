"""Слой работы с PostgreSQL.
Заменяет mock_data.py, сохраняя тот же интерфейс методов (company_id первым аргументом).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
import psycopg2
from psycopg2.extras import RealDictCursor

from .mock_data import Company, Client, Product, Order, OrderItem, Expense

D = Decimal

class PostgresDB:
    def __init__(self, dsn: str = "dbname=bizagent_db user=postgres password=postgres host=localhost port=5432"):
        self.dsn = dsn

    def _get_conn(self):
        return psycopg2.connect(self.dsn)

    # ---- Компании
    def company(self, company_id: int) -> Company | None:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name, unp, tax_regime FROM companies WHERE id = %s;", (company_id,))
                r = cur.fetchone()
                if not r:
                    return None
                return Company(r['id'], r['name'], r['unp'], r['tax_regime'])

    # ---- Клиенты
    def clients(self, company_id: int) -> list[Client]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, company_id, name, phone, email, unp, notes FROM clients WHERE company_id = %s;", (company_id,))
                rows = cur.fetchall()
                return [Client(r['id'], r['company_id'], r['name'], r['phone'], r['email'], r['unp'], r['notes']) for r in rows]

    def client(self, company_id: int, client_id: int) -> Client | None:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, company_id, name, phone, email, unp, notes FROM clients WHERE company_id = %s AND id = %s;", (company_id, client_id))
                r = cur.fetchone()
                if not r:
                    return None
                return Client(r['id'], r['company_id'], r['name'], r['phone'], r['email'], r['unp'], r['notes'])

    def add_client(self, company_id: int, *, name: str, phone=None, email=None, unp=None, notes=None) -> Client:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """INSERT INTO clients (company_id, name, phone, email, unp, notes)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;""",
                    (company_id, name, phone, email, unp, notes)
                )
                cid = cur.fetchone()['id']
                return Client(cid, company_id, name, phone, email, unp, notes)

    # ---- Товары
    def products(self, company_id: int) -> list[Product]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, company_id, sku, name, category, price, cost, stock FROM products WHERE company_id = %s;", (company_id,))
                rows = cur.fetchall()
                return [Product(r['id'], r['company_id'], r['sku'], r['name'], r['category'], D(str(r['price'])), D(str(r['cost'])), r['stock']) for r in rows]

    def product(self, company_id: int, product_id: int) -> Product | None:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, company_id, sku, name, category, price, cost, stock FROM products WHERE company_id = %s AND id = %s;", (company_id, product_id))
                r = cur.fetchone()
                if not r:
                    return None
                return Product(r['id'], r['company_id'], r['sku'], r['name'], r['category'], D(str(r['price'])), D(str(r['cost'])), r['stock'])

    # ---- Заказы
    def orders(self, company_id: int, d_from: date, d_to: date) -> list[Order]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT o.id, o.company_id, o.client_id, o.created_at, o.status
                       FROM orders o
                       WHERE o.company_id = %s AND o.status = 'completed' AND o.created_at BETWEEN %s AND %s;""",
                    (company_id, d_from, d_to)
                )
                ord_rows = cur.fetchall()
                if not ord_rows:
                    return []
                
                order_ids = [r['id'] for r in ord_rows]
                cur.execute(
                    "SELECT order_id, product_id, qty, price, unit_cost FROM order_items WHERE order_id = ANY(%s);",
                    (order_ids,)
                )
                items_by_order = {}
                for item_r in cur.fetchall():
                    oid = item_r['order_id']
                    items_by_order.setdefault(oid, []).append(
                        OrderItem(item_r['product_id'], item_r['qty'], D(str(item_r['price'])), D(str(item_r['unit_cost'])))
                    )
                
                res = []
                for r in ord_rows:
                    o = Order(r['id'], r['company_id'], r['client_id'], r['created_at'], r['status'])
                    o.items = items_by_order.get(r['id'], [])
                    res.append(o)
                return res

    def last_sale_dates(self, company_id: int) -> dict[int, date]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT oi.product_id, MAX(o.created_at) as last_date
                       FROM orders o JOIN order_items oi ON o.id = oi.order_id
                       WHERE o.company_id = %s AND o.status = 'completed'
                       GROUP BY oi.product_id;""",
                    (company_id,)
                )
                return {r['product_id']: r['last_date'] for r in cur.fetchall()}

    def client_orders(self, company_id: int, client_id: int) -> list[Order]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, company_id, client_id, created_at, status
                       FROM orders WHERE company_id = %s AND client_id = %s AND status = 'completed';""",
                    (company_id, client_id)
                )
                rows = cur.fetchall()
                return [Order(r['id'], r['company_id'], r['client_id'], r['created_at'], r['status']) for r in rows]

    def add_order(self, company_id: int, client_id: int | None, day: date, lines: list[tuple[Product, int]], status: str = "completed", decrement_stock: bool = True) -> Order:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO orders (company_id, client_id, created_at, status) VALUES (%s, %s, %s, %s) RETURNING id;",
                    (company_id, client_id, day, status)
                )
                order_id = cur.fetchone()['id']
                o = Order(order_id, company_id, client_id, day, status)
                for p, qty in lines:
                    cur.execute(
                        "INSERT INTO order_items (order_id, product_id, qty, price, unit_cost) VALUES (%s, %s, %s, %s, %s);",
                        (order_id, p.id, qty, p.price, p.cost)
                    )
                    o.items.append(OrderItem(p.id, qty, p.price, p.cost))
                    if decrement_stock:
                        cur.execute("UPDATE products SET stock = stock - %s WHERE id = %s AND company_id = %s;", (qty, p.id, company_id))
                        p.stock -= qty
                return o

    # ---- Расходы
    def expenses(self, company_id: int, d_from: date, d_to: date) -> list[Expense]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, company_id, category, amount, day, comment FROM expenses WHERE company_id = %s AND day BETWEEN %s AND %s;",
                    (company_id, d_from, d_to)
                )
                rows = cur.fetchall()
                return [Expense(r['id'], r['company_id'], r['category'], D(str(r['amount'])), r['day'], r['comment']) for r in rows]

    def add_expense(self, company_id: int, category: str, amount: Decimal, day: date, comment: str | None = None) -> Expense:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO expenses (company_id, category, amount, day, comment) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
                    (company_id, category, float(amount), day, comment)
                )
                eid = cur.fetchone()['id']
                return Expense(eid, company_id, category, amount, day, comment)