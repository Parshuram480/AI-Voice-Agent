"""Deterministic verification logic."""

from dataclasses import dataclass
from typing import Optional

from app.repositories.customer_repository import CustomerRepository


@dataclass
class VerificationResult:
    verified: bool
    customer: Optional[dict]


class VerificationService:
    """Customer verification service."""

    def __init__(self, customer_repo: CustomerRepository) -> None:
        self._customer_repo = customer_repo

    async def verify(self, name: str, dob: str) -> VerificationResult:
        customer = await self._customer_repo.get_by_name_dob(name, dob)
        return VerificationResult(verified=bool(customer), customer=customer)
