"""Session state models."""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional


@dataclass
class ConversationTurn:
    """A single turn in the conversation history."""

    role: str
    text: str
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SessionState:
    """In-memory session state for a single call."""

    session_id: str
    current_state: str
    verified: bool = False
    user_name: Optional[str] = None
    dob: Optional[str] = None
    current_intent: Optional[str] = None
    last_response: Optional[str] = None
    conversation_history: list[ConversationTurn] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    retry_counts: dict[str, int] = field(default_factory=dict)
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    last_order: Optional[dict] = None
    orders: list[dict] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)

    def add_turn(self, role: str, text: str, max_turns: int) -> None:
        self.conversation_history.append(ConversationTurn(role=role, text=text))
        if len(self.conversation_history) > max_turns:
            self.conversation_history = self.conversation_history[-max_turns:]
        self.touch()
