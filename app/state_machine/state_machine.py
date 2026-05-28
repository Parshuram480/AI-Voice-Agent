"""Deterministic conversation state machine."""

from dataclasses import dataclass
from enum import Enum

from app.models.session import SessionState


class ConversationState(str, Enum):
    IDLE = "IDLE"
    GREETING = "GREETING"
    WAITING_FOR_INTENT = "WAITING_FOR_INTENT"
    WAITING_FOR_NAME = "WAITING_FOR_NAME"
    WAITING_FOR_DOB = "WAITING_FOR_DOB"
    VERIFYING_USER = "VERIFYING_USER"
    FETCHING_ORDER = "FETCHING_ORDER"
    RESPONDING = "RESPONDING"
    FOLLOWUP = "FOLLOWUP"
    END_CALL = "END_CALL"
    FALLBACK = "FALLBACK"


@dataclass(frozen=True)
class StateTransition:
    next_state: ConversationState
    allowed: bool


class ConversationStateMachine:
    """Validates deterministic state transitions."""

    _allowed_transitions = {
        ConversationState.IDLE: {
            ConversationState.GREETING,
            ConversationState.WAITING_FOR_INTENT,
            ConversationState.END_CALL,
        },
        ConversationState.GREETING: {
            ConversationState.WAITING_FOR_INTENT,
            ConversationState.END_CALL,
        },
        ConversationState.WAITING_FOR_INTENT: {
            ConversationState.WAITING_FOR_INTENT,
            ConversationState.WAITING_FOR_NAME,
            ConversationState.WAITING_FOR_DOB,
            ConversationState.VERIFYING_USER,
            ConversationState.FETCHING_ORDER,
            ConversationState.RESPONDING,
            ConversationState.FOLLOWUP,
            ConversationState.FALLBACK,
            ConversationState.END_CALL,
        },
        ConversationState.WAITING_FOR_NAME: {
            ConversationState.WAITING_FOR_NAME,
            ConversationState.WAITING_FOR_DOB,
            ConversationState.VERIFYING_USER,
            ConversationState.FETCHING_ORDER,
            ConversationState.RESPONDING,
            ConversationState.FOLLOWUP,
            ConversationState.FALLBACK,
            ConversationState.END_CALL,
        },
        ConversationState.WAITING_FOR_DOB: {
            ConversationState.WAITING_FOR_DOB,
            ConversationState.VERIFYING_USER,
            ConversationState.FETCHING_ORDER,
            ConversationState.RESPONDING,
            ConversationState.FOLLOWUP,
            ConversationState.FALLBACK,
            ConversationState.END_CALL,
        },
        ConversationState.VERIFYING_USER: {
            ConversationState.FETCHING_ORDER,
            ConversationState.FALLBACK,
            ConversationState.END_CALL,
        },
        ConversationState.FETCHING_ORDER: {
            ConversationState.RESPONDING,
            ConversationState.FALLBACK,
        },
        ConversationState.RESPONDING: {
            ConversationState.FOLLOWUP,
            ConversationState.END_CALL,
        },
        ConversationState.FOLLOWUP: {
            ConversationState.FOLLOWUP,
            ConversationState.WAITING_FOR_INTENT,
            ConversationState.WAITING_FOR_NAME,
            ConversationState.WAITING_FOR_DOB,
            ConversationState.VERIFYING_USER,
            ConversationState.RESPONDING,
            ConversationState.FALLBACK,
            ConversationState.END_CALL,
        },
        ConversationState.FALLBACK: {
            ConversationState.WAITING_FOR_INTENT,
            ConversationState.END_CALL,
        },
        ConversationState.END_CALL: set(),
    }

    def transition(self, session: SessionState, next_state: ConversationState) -> StateTransition:
        current = ConversationState(session.current_state)
        allowed = next_state in self._allowed_transitions.get(current, set())
        return StateTransition(next_state=next_state, allowed=allowed)
