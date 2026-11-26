from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.order_register import get_order, list_orders


def test_order_register_filters_company_and_import():
    db = MagicMock()
    cursor = db._get_conn.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"exists": 1}
    cursor.fetchall.return_value = [{"id": 9}, {"id": 8}]
    start = date(2026, 11, 1)
    result = list_orders(db, 7, start, None, "EXT-1", 3, 10, limit=1)

    assert result == {"items": [{"id": 9}], "next_before": 9}
    check_import, select = cursor.execute.call_args_list
    assert check_import.args[1] == (7, 3)
    assert "o.company_id = %s" in select.args[0]
    assert select.args[1] == [7, start, 3, "EXT-1", "EXT-1", 7, 10, 2]


def test_missing_order_and_import_are_not_exposed():
    db = MagicMock()
    cursor = db._get_conn.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = None
    with pytest.raises(HTTPException) as missing_order:
        get_order(db, 7, 12)
    assert missing_order.value.status_code == 404
    assert cursor.execute.call_args.args[1] == (7, 12)
    cursor.fetchall.assert_not_called()

    with pytest.raises(HTTPException) as missing_import:
        list_orders(db, 7, None, None, None, 3, None)
    assert missing_import.value.status_code == 404
    assert cursor.execute.call_args.args[1] == (7, 3)
    cursor.fetchall.assert_not_called()
