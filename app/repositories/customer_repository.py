"""Customer repository with SQL-safe access."""

from typing import Optional

from app.database import DatabaseClient


class CustomerRepository:
    """Customer data access wrapper."""

    def __init__(self, db: DatabaseClient) -> None:
        self._db = db

    async def get_by_name_dob(self, name: str, dob: str) -> Optional[dict]:
        return await self._db.verify_customer(name, dob)

    async def soft_delete(self, customer_id: int) -> bool:
        return await self._db.soft_delete_customer(customer_id)
