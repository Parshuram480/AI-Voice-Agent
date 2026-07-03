"""Deterministic verification logic."""

from dataclasses import dataclass
from typing import Optional

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper

from app.repositories.customer_repository import CustomerRepository


@dataclass
class VerificationResult:
    verified: bool
    customer: Optional[dict]


class VerificationService:
    """Customer verification service."""

    def __init__(self, customer_repo: CustomerRepository) -> None:
        self._customer_repo = customer_repo

    @traceable(name="verify")
    async def verify(self, name: str, dob: str) -> VerificationResult:
        customer = await self._customer_repo.get_by_name_dob(name, dob)
        if customer:
            from datetime import date, datetime
            for k, v in customer.items():
                if isinstance(v, (datetime, date)):
                    customer[k] = v.isoformat()
        return VerificationResult(verified=bool(customer), customer=customer)
