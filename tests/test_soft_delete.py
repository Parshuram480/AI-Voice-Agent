import pytest
from datetime import date, datetime, UTC

from app.database import DatabaseClient, _FALLBACK_CUSTOMERS, _FALLBACK_ORDERS


@pytest.mark.anyio
async def test_soft_deleted_customer_filtered():
    db = DatabaseClient()
    db._use_fallback = True

    deleted = {
        "id": 999,
        "full_name": "Deleted User",
        "date_of_birth": date(1990, 1, 1),
        "phone": "+15550000000",
        "deleted_at": datetime.now(UTC),
    }
    _FALLBACK_CUSTOMERS.append(deleted)
    try:
        result = await db.verify_customer("Deleted User", "1990-01-01")
        assert result is None
    finally:
        _FALLBACK_CUSTOMERS.pop()


@pytest.mark.anyio
async def test_soft_deleted_order_filtered():
    db = DatabaseClient()
    db._use_fallback = True

    deleted_order = {
        "id": 999,
        "customer_id": 1,
        "order_number": "ORD-DELETED",
        "status": "Processing",
        "estimated_arrival": date(2026, 5, 30),
        "items_summary": "1x Test",
        "deleted_at": datetime.now(UTC),
    }
    _FALLBACK_ORDERS.append(deleted_order)
    try:
        orders = await db.get_all_orders(1)
        assert all(order["order_number"] != "ORD-DELETED" for order in orders)
    finally:
        _FALLBACK_ORDERS.pop()
