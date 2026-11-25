"""Import historical sales against the company's existing product catalog."""

import csv
import io
from collections import defaultdict
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

from .context import Principal


COLUMNS = ["date", "order_id", "sku", "quantity", "price"]


def import_sales(db, principal: Principal, content: bytes, confirm: bool, filename: str) -> dict:
    company_id = principal.company_id
    orders = defaultdict(list)
    errors = []
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        if reader.fieldnames != COLUMNS:
            raise HTTPException(422, "Ожидаемые колонки: " + ", ".join(COLUMNS))
        for row in reader:
            if reader.line_num > 5001:
                raise HTTPException(422, "Максимум 5000 строк")
            number = reader.line_num
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError()
                day = date.fromisoformat(row["date"].strip())
                external_id = row["order_id"].strip()
                sku = row["sku"].strip()
                quantity = int(row["quantity"])
                price = Decimal(row["price"].strip())
                if (
                    not 1 <= len(external_id) <= 100 or not 1 <= len(sku) <= 100
                    or not 1 <= quantity <= 2147483647 or not price.is_finite()
                    or not 0 <= price <= Decimal("9999999999.99")
                    or price.as_tuple().exponent < -2
                ):
                    raise ValueError()
            except (ValueError, InvalidOperation):
                errors.append({"line": number, "message": "Проверьте дату, номер заказа, артикул, количество и цену"})
                continue
            orders[external_id].append((number, day, sku, quantity, price))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise HTTPException(422, "Файл должен быть корректным CSV в кодировке UTF-8") from exc
    if not orders and not errors:
        raise HTTPException(422, "В файле нет продаж")

    with closing(db._get_conn()) as conn, conn, conn.cursor() as cur:
        if confirm:
            cur.execute("SELECT id FROM companies WHERE id = %s FOR UPDATE", (company_id,))
        cur.execute("SELECT sku, id, cost FROM products WHERE company_id = %s", (company_id,))
        products = {sku: (product_id, cost) for sku, product_id, cost in cur.fetchall()}
        cur.execute(
            "SELECT external_sale_id FROM orders WHERE company_id = %s AND external_sale_id = ANY(%s)",
            (company_id, list(orders)),
        )
        existing = {row[0] for row in cur.fetchall()}
        ready = {}
        duplicates = 0
        for external_id, lines in orders.items():
            if external_id in existing:
                duplicates += len(lines)
                continue
            valid = True
            for number, day, sku, _, _ in lines:
                if day != lines[0][1] or sku not in products:
                    errors.append({
                        "line": number,
                        "message": "Разные даты в одном заказе" if day != lines[0][1] else f"Неизвестный артикул: {sku}",
                    })
                    valid = False
            if valid:
                ready[external_id] = lines

        row_count = sum(map(len, ready.values()))
        month_revenue: dict[str, Decimal] = defaultdict(Decimal)
        month_orders: dict[str, int] = defaultdict(int)
        for lines in ready.values():
            month = lines[0][1].isoformat()[:7]
            month_revenue[month] += sum(qty * price for _, _, _, qty, price in lines)
            month_orders[month] += 1
        revenue = sum(month_revenue.values(), Decimal("0"))
        imported = 0
        if confirm and not errors:
            for external_id, lines in ready.items():
                cur.execute(
                    """INSERT INTO orders (company_id, created_at, external_sale_id)
                       VALUES (%s, %s, %s) RETURNING id""",
                    (company_id, lines[0][1], external_id),
                )
                order_id = cur.fetchone()[0]
                cur.executemany(
                    """INSERT INTO order_items (order_id, product_id, qty, price, unit_cost)
                       VALUES (%s, %s, %s, %s, %s)""",
                    [(order_id, products[sku][0], qty, price, products[sku][1])
                     for _, _, sku, qty, price in lines],
                )
                imported += 1
        if imported:
            cur.execute(
                """INSERT INTO sales_imports (company_id, user_id, author, filename, orders, rows, duplicates, revenue)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (company_id, principal.user_id, principal.name, filename, imported, row_count, duplicates, revenue),
            )
        return {
            "orders": len(ready),
            "rows": row_count,
            "duplicates": duplicates,
            "errors": sorted(errors, key=lambda error: error["line"]),
            "imported": imported,
            "revenue": str(revenue),
            "months": [
                {"month": month, "orders": month_orders[month], "revenue": str(month_revenue[month])}
                for month in sorted(month_orders)
            ],
        }

def list_sales_imports(db, company_id: int, before: int | None, limit: int = 20) -> dict:
    with closing(db._get_conn()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT id, author, user_id, filename, created_at, orders, rows, duplicates, revenue::text AS revenue
               FROM sales_imports
               WHERE company_id = %s AND (%s::bigint IS NULL OR id < %s)
               ORDER BY id DESC LIMIT %s""",
            (company_id, before, before, limit + 1),
        )
        items = [dict(row) for row in cur.fetchall()]
    return {"items": items[:limit], "next_before": items[limit - 1]["id"] if len(items) > limit else None}
