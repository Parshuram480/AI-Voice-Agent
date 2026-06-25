"""
Filler words module — natural wait-masking for voice agent latency.

Generates varied, contextually appropriate filler phrases that are
pre-synthesized into TTS audio at startup. During conversation, a random
filler is sent immediately while the pipeline processes STT/LLM/TTS,
making the wait time feel natural.

Key design principles:
  - Never repeat the same filler consecutively
  - Use varied, natural phrases (not just "Hmm" every time)
  - Fillers are context-aware (different for first turn vs. follow-up)
"""

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

# Filler phrases organized by context
FILLER_POOLS = {
    # General thinking fillers — used when processing any turn
    "thinking": [
        "Let me check that for you.",
        "One moment please.",
        "Let me look into that.",
        "Just a moment.",
        "Sure, let me see.",
        "Alright, checking now.",
        "Give me just a second.",
        "Let me pull that up.",
    ],
    # Acknowledgment fillers — used after receiving user input
    "acknowledge": [
        "Got it.",
        "Okay.",
        "Sure thing.",
        "Alright.",
        "Understood.",
        "Right.",
    ],
    # Greeting fillers — used for first turn
    "greeting": [
        "Hello! Let me help you with that.",
        "Hi there! One moment.",
    ],
}


class FillerManager:
    """
    Manages randomized filler word selection with anti-repetition.

    Usage:
        filler_mgr = FillerManager()
        phrase = filler_mgr.get_filler("thinking")
        # -> "Let me check that for you."
        phrase = filler_mgr.get_filler("thinking")
        # -> "One moment please."  (different from last)
    """

    def __init__(self):
        self._last_used: dict[str, str] = {}
        self._usage_counts: dict[str, int] = {}

    def get_filler(self, context: str = "thinking") -> str:
        """
        Get a random filler phrase for the given context.

        Ensures the same phrase is never used consecutively.

        Args:
            context: One of "thinking", "acknowledge", "greeting".

        Returns:
            A filler phrase string.
        """
        pool = FILLER_POOLS.get(context, FILLER_POOLS["thinking"])
        last = self._last_used.get(context)

        # Filter out the last-used phrase to avoid repetition
        candidates = [p for p in pool if p != last]
        if not candidates:
            candidates = pool

        phrase = random.choice(candidates)
        self._last_used[context] = phrase

        # Track usage for analytics
        self._usage_counts[phrase] = self._usage_counts.get(phrase, 0) + 1

        return phrase

    def get_filler_for_turn(self, turn_index: int) -> str:
        """
        Get an appropriate filler for the current turn.

        Args:
            turn_index: The current conversation turn number (0-based).

        Returns:
            A contextually appropriate filler phrase.
        """
        if turn_index == 0:
            return self.get_filler("greeting")
        elif turn_index <= 2:
            # Early turns — use acknowledgments more
            return self.get_filler("acknowledge")
        else:
            # Later turns — mix thinking and acknowledgment
            context = random.choice(["thinking", "acknowledge"])
            return self.get_filler(context)

    @property
    def stats(self) -> dict:
        """Return usage statistics for debugging."""
        return dict(self._usage_counts)
