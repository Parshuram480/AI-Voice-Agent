from dataclasses import dataclass, field
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
    turn_metrics: dict = field(default_factory=dict)
