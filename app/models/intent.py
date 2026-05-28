"""Intent model definitions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentResult:
    """Deterministic intent routing result."""

    intent: str
    confidence: float
    reason: str = ""
