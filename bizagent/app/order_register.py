"""Read-only order register scoped to the authenticated company."""

from contextlib import closing
from datetime import date

from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

ORDER_COLUMNS = """
    o.id, o.external_sale_id, o.sales_import_id, o.created_at, o.status,
    c.name AS client,
    COALESCE((SELECT SUM(i.qty * i.price) FROM order_items i WHERE i.order_id = o.id), 0)::text AS total
"""
ORDER_SOURCE = """
    FROM orders o
    LEFT JOIN clients c ON c.id = o.client_id AND c.company_id = o.company_id
"""


def list_orders(db, company_id: int, date_from: date | None, date_to: date | None,
                number: str | None, import_id: int | None, before: int | None, limit: int = 25) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Начало периода должно быть не позже конца")
    filters = ["o.company_id = %s"]
    params = [company_id]
    for clause, value in (
        ("o.created_at >= %s", date_from),
        ("o.created_at <= %s", date_to),
        ("o.sales_import_id = %s", import_id),
    ):
        if value is not None:
            filters.append(clause)
            params.append(value)
    if number:
        filters.append("(o.id::text = %s OR LOWER(o.external_sale_id) = LOWER(%s))")
        params.extend([number, number])
    if before is not None:
        filters.append("""(o.created_at, o.id) < (
            SELECT created_at, id FROM orders WHERE company_id = %s AND id = %s
        )""")
        params.extend([company_id, before])

    with closing(db._get_conn()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        if import_id is not None:
            cur.execute("SELECT 1 FROM sales_imports WHERE company_id = %s AND id = %s", (company_id, import_id))
            if cur.fetchone() is None:
                raise HTTPException(404, "Импорт не найден")
        where = " AND ".join(filters)
        cur.execute(
            f"""SELECT {ORDER_COLUMNS} {ORDER_SOURCE} WHERE {where}
                ORDER BY o.created_at DESC, o.id DESC LIMIT %s""",
            [*params, limit + 1],
        )
        items = cur.fetchall()
    return {"items": items[:limit], "next_before": items[limit - 1]["id"] if len(items) > limit else None}


def get_order(db, company_id: int, order_id: int) -> dict:
    with closing(db._get_conn()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"SELECT {ORDER_COLUMNS} {ORDER_SOURCE} WHERE o.company_id = %s AND o.id = %s",
            (company_id, order_id),
        )
        order = cur.fetchone()
        if order is None:
            raise HTTPException(404, "Заказ не найден")
        cur.execute(
            """SELECT i.id, p.sku, p.name, i.qty, i.price::text AS price, (i.qty * i.price)::text AS total
               FROM order_items i
               JOIN orders o ON o.id = i.order_id AND o.company_id = %s
               JOIN products p ON p.id = i.product_id AND p.company_id = o.company_id
               WHERE i.order_id = %s ORDER BY i.id""",
            (company_id, order_id),
        )
        return {**order, "lines": cur.fetchall()}
