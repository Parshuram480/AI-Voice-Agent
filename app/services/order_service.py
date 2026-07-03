"""Order lookup service."""

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper

from app.repositories.order_repository import OrderRepository


class OrderService:
    """Order lookup service wrapper."""

    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo

    @traceable(name="get_orders")
    async def get_orders(self, customer_id: int) -> list[dict]:
        orders = await self._order_repo.get_all_for_customer(customer_id)
        # Convert datetime objects to strings for JSON serialization (fixes UI and LangSmith crashes)
        from datetime import date, datetime
        for o in orders:
            for k, v in o.items():
                if isinstance(v, (datetime, date)):
                    o[k] = v.isoformat()
        return orders

    async def get_latest_order(self, customer_id: int) -> dict | None:
        order = await self._order_repo.get_latest_for_customer(customer_id)
        if order:
            from datetime import date, datetime
            for k, v in order.items():
                if isinstance(v, (datetime, date)):
                    order[k] = v.isoformat()
        return order
