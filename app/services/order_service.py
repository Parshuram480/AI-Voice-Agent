"""Order lookup service."""

from app.repositories.order_repository import OrderRepository


class OrderService:
    """Order lookup service wrapper."""

    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo

    async def get_orders(self, customer_id: int) -> list[dict]:
        return await self._order_repo.get_all_for_customer(customer_id)

    async def get_latest_order(self, customer_id: int) -> dict | None:
        return await self._order_repo.get_latest_for_customer(customer_id)
