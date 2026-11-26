from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.context import Principal
from app.workflows import PurchaseDraft, StaffUpdate, reverse_import, save_purchase, update_staff

OWNER = Principal(3, 7, "owner", "Анна")


def db_cursor():
    db = MagicMock()
    return db, db._get_conn.return_value.cursor.return_value.__enter__.return_value


def test_import_reversal_reports_impact_and_keeps_history():
    db, cursor = db_cursor()
    batch = {"id": 2, "filename": "sales.csv", "reversed_at": None}
    periods = [{"month": "2026-11-01", "orders": 2, "revenue": "120.50"}]
    cursor.fetchone.return_value = dict(batch)
    cursor.fetchall.return_value = periods
    assert reverse_import(db, OWNER, 2, False)["periods"] == periods
    assert all("UPDATE" not in call.args[0] for call in cursor.execute.call_args_list)

    when = datetime(2026, 11, 26, tzinfo=timezone.utc)
    cursor.fetchone.side_effect = [dict(batch), {"reversed_at": when, "reversed_by_name": "Анна"}]
    assert reverse_import(db, OWNER, 2, True)["reversed_at"] == when
    writes = [call for call in cursor.execute.call_args_list if call.args[0].startswith("UPDATE")]
    assert len(writes) == 2
    assert writes[0].args[1] == (7, 2)
    assert writes[1].args[1] == (3, "Анна", 7, 2)

    cursor.execute.reset_mock()
    cursor.fetchone.side_effect = None
    cursor.fetchone.return_value = {**batch, "reversed_at": when}
    cursor.fetchall.return_value = []
    assert reverse_import(db, OWNER, 2, True)["reversed_at"] == when
    assert not any(call.args[0].startswith("UPDATE") for call in cursor.execute.call_args_list)


def test_purchase_validates_company_catalog_and_retries_by_request_id():
    db, cursor = db_cursor()
    draft = PurchaseDraft(supplier=" Опт ", lines=[{"product_id": 5, "quantity": 4}])
    request_id = UUID("00000000-0000-0000-0000-000000000001")
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    with pytest.raises(HTTPException) as exc:
        save_purchase(db, OWNER, draft, request_id)
    assert exc.value.status_code == 422
    assert cursor.execute.call_args.args[1] == (7, [5])
    cursor.executemany.assert_not_called()

    cursor.fetchall.return_value = [{"id": 5, "name": "Товар", "sku": "SKU"}]
    cursor.fetchone.side_effect = [None, {"id": 9}, {"id": 9}]
    assert save_purchase(db, OWNER, draft, request_id) == {"id": 9}
    assert cursor.executemany.call_args.args[1] == [(9, 5, "Товар", "SKU", 4)]
    assert save_purchase(db, OWNER, draft, request_id) == {"id": 9}
    assert cursor.executemany.call_count == 1


def test_staff_changes_are_scoped_and_invalidate_sessions():
    db, cursor = db_cursor()
    update = StaffUpdate(role="manager", active=False)
    with pytest.raises(HTTPException) as exc:
        update_staff(db, OWNER, 3, update)
    assert exc.value.status_code == 409
    db._get_conn.assert_not_called()

    cursor.fetchone.side_effect = [{"role": "owner", "active": True}, {"id": 4, "active": False}]
    assert update_staff(db, OWNER, 4, update)["active"] is False
    statement, values = cursor.execute.call_args.args
    assert "session_version = session_version +" in statement
    assert values == ("manager", False, False, "manager", 7, 4)
