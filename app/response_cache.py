"""
Response cache — LRU cache for TTS audio bytes.

Avoids re-synthesizing identical text replies (e.g. "Your order has been shipped").
Keyed by exact reply text.  Bounded by max_size with LRU eviction.
"""

import logging
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)


class ResponseCache:
    """
    Thread-safe (single-event-loop) LRU cache for TTS audio bytes.

    Usage:
        cache = ResponseCache(max_size=100)
        audio = cache.get("Hello there")
        if audio is None:
            audio = await groq.text_to_speech("Hello there")
            cache.put("Hello there", audio)
    """

    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def get(self, text: str) -> Optional[bytes]:
        """Return cached audio bytes for *text*, or None on miss."""
        key = text.strip()
        if key in self._cache:
            # Move to end (most-recently-used)
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug(f"Cache HIT  (hits={self._hits}): '{key[:60]}…'")
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, text: str, audio: bytes) -> None:
        """Store *audio* bytes keyed by *text*, evicting LRU if full."""
        key = text.strip()
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = audio
            return
        if len(self._cache) >= self._max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug(f"Cache EVICT: '{evicted_key[:60]}…'")
        self._cache[key] = audio

    def clear(self) -> None:
        """Flush the entire cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total else 0.0,
        }
