from unittest.mock import MagicMock
from decimal import Decimal

from app.context import Principal

from app.sales_import import import_sales, list_sales_imports


PRINCIPAL = Principal(user_id=3, company_id=7, role="owner", name="Анна")
FILENAME = "sales.csv"
CSV = b"date,order_id,sku,quantity,price\n2026-11-20,EXT-1,ONE,2,15.50\n2026-11-20,EXT-1,TWO,1,10.00\n"


def test_sales_import_preview_confirm_and_duplicate():
    db = MagicMock()
    cursor = db._get_conn.return_value.cursor.return_value.__enter__.return_value
    products = [("ONE", 11, 5), ("TWO", 12, 4)]
    cursor.fetchall.side_effect = [products, [], products, [], products, [("EXT-1",)]]
    cursor.fetchone.return_value = (42,)

    preview = import_sales(db, PRINCIPAL, CSV, confirm=False, filename=FILENAME)
    assert preview == {
        "orders": 1, "rows": 2, "duplicates": 0,
        "errors": [], "imported": 0, "revenue": "41.00",
        "months": [{"month": "2026-11", "orders": 1, "revenue": "41.00"}],
    }
    cursor.executemany.assert_not_called()

    assert import_sales(db, PRINCIPAL, CSV, confirm=True, filename=FILENAME)["imported"] == 1
    assert cursor.executemany.call_args.args[1] == [
        (42, 11, 2, 15.50, 5), (42, 12, 1, 10.00, 4),
    ]

    history_inserts = [call for call in cursor.execute.call_args_list if "INSERT INTO sales_imports" in call.args[0]]
    assert len(history_inserts) == 1
    assert history_inserts[0].args[1] == (7, 3, "Анна", FILENAME, 1, 2, 0, Decimal("41.00"))

    repeated = import_sales(db, PRINCIPAL, CSV, confirm=True, filename=FILENAME)
    assert repeated["duplicates"] == 2
    assert repeated["imported"] == 0
    assert repeated["months"] == []
    assert cursor.executemany.call_count == 1
    assert sum("INSERT INTO sales_imports" in call.args[0] for call in cursor.execute.call_args_list) == 1


def test_invalid_line_blocks_entire_import():
    db = MagicMock()
    cursor = db._get_conn.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [[("ONE", 11, 5)], []]
    result = import_sales(db, PRINCIPAL, CSV, confirm=True, filename=FILENAME)
    assert result["errors"] == [{"line": 3, "message": "Неизвестный артикул: TWO"}]
    assert result["imported"] == 0
    cursor.executemany.assert_not_called()

def test_import_history_filters_company_and_paginates():
    db = MagicMock()
    cursor = db._get_conn.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [{"id": 9}, {"id": 8}, {"id": 7}]
    assert list_sales_imports(db, 7, before=10, limit=2) == {
        "items": [{"id": 9}, {"id": 8}],
        "next_before": 8,
    }
    assert "WHERE company_id = %s" in cursor.execute.call_args.args[0]
    assert cursor.execute.call_args.args[1] == (7, 10, 10, 3)
