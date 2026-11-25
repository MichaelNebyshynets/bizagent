"""PostgreSQL operations for import reversal, purchases and staff."""

from contextlib import closing
from typing import Literal

from fastapi import HTTPException
from psycopg2.errors import UniqueViolation
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field, field_validator

from .auth import hash_password
from .context import Principal

Role = Literal["owner", "manager", "accountant"]


class PurchaseLine(BaseModel):
    product_id: int = Field(ge=1, le=2**31 - 1)
    quantity: int = Field(ge=1, le=1_000_000)


class PurchaseDraft(BaseModel):
    supplier: str = Field(min_length=1, max_length=255)
    lines: list[PurchaseLine] = Field(min_length=1, max_length=100)

    @field_validator("supplier", mode="before")
    @classmethod
    def trim_supplier(cls, value):
        return value.strip() if isinstance(value, str) else value


class StaffCreate(BaseModel):
    email: str = Field(max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    name: str = Field(min_length=1, max_length=255)
    role: Role
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email", "name", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class StaffUpdate(BaseModel):
    role: Role
    active: bool


def reverse_import(db, principal: Principal, import_id: int, confirm: bool) -> dict:
    with closing(db._get_conn()) as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        if confirm:
            cur.execute("SELECT id FROM companies WHERE id = %s FOR UPDATE", (principal.company_id,))
        cur.execute(
            """SELECT id, filename, reversed_at, reversed_by, reversed_by_name FROM sales_imports
               WHERE company_id = %s AND id = %s""",
            (principal.company_id, import_id),
        )
        batch = cur.fetchone()
        if batch is None:
            raise HTTPException(404, "Импорт не найден")
        cur.execute(
            """SELECT date_trunc('month', o.created_at)::date AS month, COUNT(DISTINCT o.id) AS orders,
                      COALESCE(SUM(i.qty * i.price), 0)::text AS revenue
               FROM orders o LEFT JOIN order_items i ON i.order_id = o.id
               WHERE o.company_id = %s AND o.sales_import_id = %s AND o.status = 'completed'
               GROUP BY month ORDER BY month""",
            (principal.company_id, import_id),
        )
        periods = cur.fetchall()
        if not periods and batch["reversed_at"] is None:
            raise HTTPException(409, "У этой загрузки нет связанных заказов для отмены")
        if confirm and batch["reversed_at"] is None:
            cur.execute(
                """UPDATE orders SET status = 'cancelled'
                   WHERE company_id = %s AND sales_import_id = %s AND status = 'completed'""",
                (principal.company_id, import_id),
            )
            cur.execute(
                """UPDATE sales_imports SET reversed_at = CURRENT_TIMESTAMP, reversed_by = %s,
                          reversed_by_name = %s
                   WHERE company_id = %s AND id = %s RETURNING reversed_at, reversed_by, reversed_by_name""",
                (principal.user_id, principal.name, principal.company_id, import_id),
            )
            batch.update(cur.fetchone())
        return {**batch, "periods": periods}


def purchase_options(db, company_id: int) -> dict:
    with closing(db._get_conn()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT id, sku, name, stock FROM products
               WHERE company_id = %s ORDER BY stock, name, id""",
            (company_id,),
        )
        products = cur.fetchall()
        cur.execute(
            """SELECT p.*, (
                 SELECT json_agg(json_build_object('name', i.product_name, 'sku', i.sku,
                     'quantity', i.quantity) ORDER BY i.product_id)
                 FROM purchase_order_items i WHERE i.purchase_order_id = p.id
               ) AS lines
               FROM purchase_orders p WHERE p.company_id = %s ORDER BY p.id DESC LIMIT 50""",
            (company_id,),
        )
        return {"products": products, "orders": cur.fetchall()}


def save_purchase(db, principal: Principal, draft: PurchaseDraft, request_id) -> dict:
    quantities = {line.product_id: line.quantity for line in draft.lines}
    if len(quantities) != len(draft.lines):
        raise HTTPException(422, "Один товар можно добавить только один раз")
    with closing(db._get_conn()) as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT id FROM purchase_orders WHERE company_id = %s AND request_id = %s""",
            (principal.company_id, str(request_id)),
        )
        previous = cur.fetchone()
        if previous is not None:
            return previous
        cur.execute(
            "SELECT id, name, sku FROM products WHERE company_id = %s AND id = ANY(%s) FOR SHARE",
            (principal.company_id, list(quantities)),
        )
        products = cur.fetchall()
        if len(products) != len(quantities):
            raise HTTPException(422, "Один из товаров недоступен в каталоге компании")
        cur.execute(
            """INSERT INTO purchase_orders (company_id, user_id, author, supplier, request_id)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (company_id, request_id) DO NOTHING RETURNING id""",
            (principal.company_id, principal.user_id, principal.name, draft.supplier, str(request_id)),
        )
        order = cur.fetchone()
        if order is None:
            cur.execute(
                "SELECT id FROM purchase_orders WHERE company_id = %s AND request_id = %s",
                (principal.company_id, str(request_id)),
            )
            return cur.fetchone()
        cur.executemany(
            """INSERT INTO purchase_order_items (purchase_order_id, product_id, product_name, sku, quantity)
               VALUES (%s, %s, %s, %s, %s)""",
            [(order["id"], p["id"], p["name"], p["sku"], quantities[p["id"]]) for p in products],
        )
        return order


def list_staff(db, company_id: int) -> list:
    with closing(db._get_conn()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, name, email, role, active FROM users WHERE company_id = %s ORDER BY name, id",
            (company_id,),
        )
        return cur.fetchall()


def lock_staff_owner(cur, principal: Principal) -> None:
    cur.execute("SELECT id FROM companies WHERE id = %s FOR UPDATE", (principal.company_id,))
    cur.execute(
        "SELECT role, active FROM users WHERE company_id = %s AND id = %s",
        (principal.company_id, principal.user_id),
    )
    actor = cur.fetchone()
    if actor is None or not actor["active"] or actor["role"] != "owner":
        raise HTTPException(403, "Управление сотрудниками доступно владельцу")


def create_staff(db, principal: Principal, body: StaffCreate) -> dict:
    password_hash = hash_password(body.password)
    try:
        with closing(db._get_conn()) as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            lock_staff_owner(cur, principal)
            cur.execute(
                """INSERT INTO users (company_id, email, name, role, password_hash)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id, email, name, role, active""",
                (principal.company_id, body.email.lower(), body.name, body.role, password_hash),
            )
            return cur.fetchone()
    except UniqueViolation as exc:
        raise HTTPException(409, "Этот email уже используется") from exc


def update_staff(db, principal: Principal, user_id: int, body: StaffUpdate) -> dict:
    if principal.user_id == user_id:
        raise HTTPException(409, "Свою роль и доступ здесь изменить нельзя")
    with closing(db._get_conn()) as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        lock_staff_owner(cur, principal)
        cur.execute(
            """UPDATE users SET role = %s, active = %s,
                   session_version = session_version + CASE WHEN active <> %s OR role <> %s THEN 1 ELSE 0 END
               WHERE company_id = %s AND id = %s RETURNING id, email, name, role, active""",
            (body.role, body.active, body.active, body.role, principal.company_id, user_id),
        )
        staff = cur.fetchone()
        if staff is None:
            raise HTTPException(404, "Сотрудник не найден")
        return staff
