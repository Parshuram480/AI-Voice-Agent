"""Conversation response models."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConversationResult:
    """Structured result of a conversation turn."""

    session_id: str
    intent: str
    reply_text: str
    state: str
    should_end: bool
    verified: bool
    customer: Optional[dict]
    orders: list[dict]
    timings: dict[str, float]
