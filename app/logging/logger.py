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


import os
from datetime import datetime

TRANSCRIPTS_DIR = "transcripts"

def log_transcript(session_id: str, user_text: str, agent_text: str, latency_str: str = "") -> None:
    """Log the raw user input and agent response to a session-specific file."""
    if not os.path.exists(TRANSCRIPTS_DIR):
        os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
        
    filepath = os.path.join(TRANSCRIPTS_DIR, f"{session_id}.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"[{timestamp}]"
    if latency_str:
        header += f" (Latency: {latency_str})"
    
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(f"{header}\n")
        f.write(f"user: \"{user_text}\"\n")
        f.write(f"agent: \"{agent_text}\"\n\n")
