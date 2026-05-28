"""Structured logging utilities for the voice agent pipeline.

Provides structured JSON logging with session_id, utterance_id,
and timing fields for every event in the conversational pipeline.
"""

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("voice_agent")


def log_event(event: str, **fields: Any) -> None:
    """Log a structured event with arbitrary key-value fields."""
    payload = {"event": event, **fields}
    try:
        logger.info(json.dumps(payload, default=str))
    except Exception:
        logger.info("event=%s fields=%s", event, fields)


def log_pipeline_event(
    event: str,
    *,
    session_id: Optional[str] = None,
    utterance_id: Optional[str] = None,
    turn_index: Optional[int] = None,
    duration_ms: Optional[float] = None,
    **extra: Any,
) -> None:
    """Log a pipeline event with standard session/utterance context."""
    payload: dict[str, Any] = {
        "event": event,
        "ts": time.time(),
    }
    if session_id is not None:
        payload["session_id"] = session_id
    if utterance_id is not None:
        payload["utterance_id"] = utterance_id
    if turn_index is not None:
        payload["turn_index"] = turn_index
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    payload.update(extra)
    try:
        logger.info(json.dumps(payload, default=str))
    except Exception:
        logger.info("event=%s fields=%s", event, payload)
