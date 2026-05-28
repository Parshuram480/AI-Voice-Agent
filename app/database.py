"""
Database client — async PostgreSQL access via asyncpg.

Provides customer verification and order lookup for the voice pipeline.
Falls back to an in-memory store when PostgreSQL is unavailable,
so the system can still be tested locally without a database.
"""

import logging
from datetime import date, datetime, UTC
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Try to import asyncpg; allow graceful fallback
try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    asyncpg = None
    HAS_ASYNCPG = False
    logger.warning("asyncpg not installed — using in-memory fallback database.")


# =============================================================================
# In-memory fallback data (mirrors sql/init.sql sample data)
# =============================================================================
_FALLBACK_CUSTOMERS = [
    {
        "id": 1,
        "full_name": "John Smith",
        "date_of_birth": date(1990, 5, 15),
        "phone": "+15551234567",
        "deleted_at": None,
    },
    {
        "id": 2,
        "full_name": "Jane Doe",
        "date_of_birth": date(1985, 11, 20),
        "phone": "+15559876543",
        "deleted_at": None,
    },
    {
        "id": 3,
        "full_name": "Alice Johnson",
        "date_of_birth": date(1992, 3, 8),
        "phone": "+15554567890",
        "deleted_at": None,
    },
]

_FALLBACK_ORDERS = [
    {
        "id": 1,
        "customer_id": 1,
        "order_number": "ORD-20260501-001",
        "status": "Shipped",
        "estimated_arrival": date(2026, 5, 25),
        "items_summary": "2x Wireless Headphones, 1x USB-C Cable",
        "deleted_at": None,
    },
    {
        "id": 2,
        "customer_id": 1,
        "order_number": "ORD-20260510-002",
        "status": "Processing",
        "estimated_arrival": date(2026, 5, 28),
        "items_summary": "1x Mechanical Keyboard",
        "deleted_at": None,
    },
    {
        "id": 3,
        "customer_id": 2,
        "order_number": "ORD-20260505-003",
        "status": "Delivered",
        "estimated_arrival": date(2026, 5, 18),
        "items_summary": "3x Phone Case, 1x Screen Protector",
        "deleted_at": None,
    },
    {
        "id": 4,
        "customer_id": 3,
        "order_number": "ORD-20260512-004",
        "status": "In Transit",
        "estimated_arrival": date(2026, 5, 24),
        "items_summary": "1x Laptop Stand, 2x Monitor Riser",
        "deleted_at": None,
    },
]


class DatabaseClient:
    """
    Async database client for customer verification and order lookups.

    Connects to PostgreSQL via asyncpg when available, otherwise uses
    an in-memory fallback with sample data for local testing.
    """

    def __init__(self):
        self._pool: Optional[object] = None
        self._use_fallback = False

    @property
    def use_fallback(self) -> bool:
        return self._use_fallback

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    async def connect(self):
        """Initialize the database connection pool."""
        if not HAS_ASYNCPG or not settings.DB_PASSWORD:
            logger.info("Using in-memory fallback database (no asyncpg or DB_PASSWORD not set).")
            self._use_fallback = True
            return

        try:
            self._pool = await asyncpg.create_pool(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                database=settings.DB_NAME,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                min_size=2,
                max_size=10,
                command_timeout=5,
            )
            logger.info(f"Connected to PostgreSQL at {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
        except Exception as e:
            logger.warning(f"Could not connect to PostgreSQL: {e}. Using in-memory fallback.")
            self._use_fallback = True

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL connection pool closed.")

    # -------------------------------------------------------------------------
    # Customer Verification
    # -------------------------------------------------------------------------
    async def verify_customer(self, name: str, dob: str) -> Optional[dict]:
        """
        Verify a customer by full name and date of birth.

        Args:
            name: Customer's full name (case-insensitive match).
            dob: Date of birth as a string "YYYY-MM-DD".

        Returns:
            Customer dict {"id", "full_name", "date_of_birth", "phone"} or None.
        """
        if self._use_fallback:
            return self._fallback_verify_customer(name, dob)

        query = """
            SELECT id, full_name, date_of_birth, phone
            FROM customers
            WHERE LOWER(full_name) = LOWER($1)
              AND date_of_birth = $2
                            AND deleted_at IS NULL
            LIMIT 1;
        """
        try:
            dob_date = date.fromisoformat(dob) if isinstance(dob, str) else dob
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, name, dob_date)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"DB error in verify_customer: {e}")
            return None

    def _fallback_verify_customer(self, name: str, dob: str) -> Optional[dict]:
        """In-memory customer lookup."""
        try:
            dob_date = date.fromisoformat(dob) if isinstance(dob, str) else dob
        except ValueError:
            return None

        for c in _FALLBACK_CUSTOMERS:
            if c.get("deleted_at") is not None:
                continue
            if c["full_name"].lower() == name.lower() and c["date_of_birth"] == dob_date:
                return c
        return None

    # -------------------------------------------------------------------------
    # Order Lookup
    # -------------------------------------------------------------------------
    async def get_latest_order(self, customer_id: int) -> Optional[dict]:
        """
        Retrieve the most recent order for a customer.

        Args:
            customer_id: The customer's database ID.

        Returns:
            Order dict {"order_number", "status", "estimated_arrival", "items_summary"} or None.
        """
        if self._use_fallback:
            return self._fallback_get_latest_order(customer_id)

        query = """
            SELECT order_number, status, estimated_arrival, items_summary, created_at
            FROM orders
            WHERE customer_id = $1
              AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1;
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, customer_id)
            if row:
                result = dict(row)
                # Convert date objects to strings for JSON serialization
                if result.get("estimated_arrival"):
                    result["estimated_arrival"] = result["estimated_arrival"].isoformat()
                if result.get("created_at"):
                    result["created_at"] = result["created_at"].isoformat()
                return result
            return None
        except Exception as e:
            logger.error(f"DB error in get_latest_order: {e}")
            return None

    def _fallback_get_latest_order(self, customer_id: int) -> Optional[dict]:
        """In-memory order lookup — returns the latest order for the given customer."""
        customer_orders = [
            o for o in _FALLBACK_ORDERS
            if o["customer_id"] == customer_id and o.get("deleted_at") is None
        ]
        if not customer_orders:
            return None
        latest = customer_orders[-1]  # Last one is the most recent
        return {
            "order_number": latest["order_number"],
            "status": latest["status"],
            "estimated_arrival": latest["estimated_arrival"].isoformat() if latest.get("estimated_arrival") else None,
            "items_summary": latest.get("items_summary", ""),
        }

    # -------------------------------------------------------------------------
    # Get all orders for a customer
    # -------------------------------------------------------------------------
    async def get_all_orders(self, customer_id: int) -> list[dict]:
        """Retrieve all orders for a customer, most recent first."""
        if self._use_fallback:
            return self._fallback_get_all_orders(customer_id)

        query = """
            SELECT order_number, status, estimated_arrival, items_summary, created_at
            FROM orders
            WHERE customer_id = $1
              AND deleted_at IS NULL
            ORDER BY created_at DESC;
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, customer_id)
            results = []
            for row in rows:
                r = dict(row)
                if r.get("estimated_arrival"):
                    r["estimated_arrival"] = r["estimated_arrival"].isoformat()
                if r.get("created_at"):
                    r["created_at"] = r["created_at"].isoformat()
                results.append(r)
            return results
        except Exception as e:
            logger.error(f"DB error in get_all_orders: {e}")
            return []

    def _fallback_get_all_orders(self, customer_id: int) -> list[dict]:
        """In-memory: all orders for a customer."""
        return [
            {
                "order_number": o["order_number"],
                "status": o["status"],
                "estimated_arrival": o["estimated_arrival"].isoformat() if o.get("estimated_arrival") else None,
                "items_summary": o.get("items_summary", ""),
            }
            for o in reversed(_FALLBACK_ORDERS)
            if o["customer_id"] == customer_id and o.get("deleted_at") is None
        ]

    # -------------------------------------------------------------------------
    # Soft Delete
    # -------------------------------------------------------------------------
    async def soft_delete_customer(self, customer_id: int) -> bool:
        if self._use_fallback:
            for customer in _FALLBACK_CUSTOMERS:
                if customer["id"] == customer_id and customer.get("deleted_at") is None:
                    customer["deleted_at"] = datetime.now(UTC)
                    return True
            return False

        query = """
            UPDATE customers
            SET deleted_at = NOW()
            WHERE id = $1
              AND deleted_at IS NULL;
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, customer_id)
            return result.endswith("UPDATE 1")
        except Exception as e:
            logger.error(f"DB error in soft_delete_customer: {e}")
            return False

    async def soft_delete_order(self, order_id: int) -> bool:
        if self._use_fallback:
            for order in _FALLBACK_ORDERS:
                if order["id"] == order_id and order.get("deleted_at") is None:
                    order["deleted_at"] = datetime.now(UTC)
                    return True
            return False

        query = """
            UPDATE orders
            SET deleted_at = NOW()
            WHERE id = $1
              AND deleted_at IS NULL;
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, order_id)
            return result.endswith("UPDATE 1")
        except Exception as e:
            logger.error(f"DB error in soft_delete_order: {e}")
            return False
