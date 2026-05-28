"""Order repository with SQL-safe access."""

from app.database import DatabaseClient


class OrderRepository:
    """Order data access wrapper."""

    def __init__(self, db: DatabaseClient) -> None:
        self._db = db

    async def get_latest_for_customer(self, customer_id: int) -> dict | None:
        return await self._db.get_latest_order(customer_id)

    async def get_all_for_customer(self, customer_id: int) -> list[dict]:
        return await self._db.get_all_orders(customer_id)

    async def soft_delete(self, order_id: int) -> bool:
        return await self._db.soft_delete_order(order_id)
