"""Request schemas."""

from pydantic import BaseModel


class SimulateRequest(BaseModel):
    """Request body for the /api/simulate endpoint."""

    name: str = "John Smith"
    dob: str = "1990-05-15"
    query: str = "What is my order status?"
