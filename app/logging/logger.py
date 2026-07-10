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

HISTORIES_DIR = "histories"

def log_history(session_id: str, state: dict) -> None:
    """Save the conversation history state to a JSON file."""
    if not os.path.exists(HISTORIES_DIR):
        os.makedirs(HISTORIES_DIR, exist_ok=True)
        
    filepath = os.path.join(HISTORIES_DIR, f"{session_id}.json")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state.get("messages", []), f, indent=2)
    except Exception as e:
        logger.error(f"Failed to log history for {session_id}: {e}")

METRICS_DIR = "metrics"


def _calculate_total_ttft(metrics: dict) -> str:
    from datetime import datetime
    try:
        if 'timing_tool_start' in metrics and 'timing_tool_end' in metrics:
            start = datetime.strptime(metrics['timing_tool_start'], "%H:%M:%S.%f")
            end = datetime.strptime(metrics['timing_tool_end'], "%H:%M:%S.%f")
            tool_dur = (end - start).total_seconds()
            
            llm1_tot = float(metrics.get('llm1_total_time', 0.0))
            llm2_ttft = float(metrics.get('llm2_ttft', 0.0))
            return f"{(llm1_tot + tool_dur + llm2_ttft):.4f}"
        else:
            return f"{float(metrics.get('llm1_ttft', 0.0)):.4f}"
    except Exception as e:
        return f"ERROR ({e})"

def log_llm_metrics(session_id: str, metrics: dict) -> None:
    """Log LLM metrics to a session-specific file."""
    if not os.path.exists(METRICS_DIR):
        os.makedirs(METRICS_DIR, exist_ok=True)
        
    filepath = os.path.join(METRICS_DIR, f"{session_id}.txt")
    
    content = [
        "=========================",
        "APPLICATION OVERHEAD",
        "=========================",
        f"User Finished Speaking:      {metrics.get('timing_user_finished', 'N/A')}",
        f"STT Final Transcript:        {metrics.get('timing_stt_final_transcript', 'N/A')}",
        f"Queue Wait End:              {metrics.get('timing_queue_wait_end', 'N/A')}",
        f"Memory Retrieval Start:      {metrics.get('timing_memory_retrieval_start', 'N/A')}",
        f"Memory Retrieval End:        {metrics.get('timing_memory_retrieval_end', 'N/A')}",
        f"State Update Start:          {metrics.get('timing_state_update_start', 'N/A')}",
        f"State Update End:            {metrics.get('timing_state_update_end', 'N/A')}",
        f"Serialization Start:         {metrics.get('timing_serialization_start', 'N/A')}",
        f"Serialization End:           {metrics.get('timing_serialization_end', 'N/A')}",
        f"Calculated E2E TTFT (LLM1+Tool+LLM2): {_calculate_total_ttft(metrics)}s",
        f"Actual Total Server Latency (Inc. VAD, STT, TTS): {metrics.get('ttfa_total_ms', 'N/A')}ms",
        "=========================",
        "LLM 1 (ROUTING)",
        "=========================",
        f"Prompt Tokens: {metrics.get('llm1_prompt_tokens', 0)}",
        f"Completion Tokens: {metrics.get('llm1_completion_tokens', 0)}",
        f"TTFT: {metrics.get('llm1_ttft', '0.0')}s",
        f"Generation Time: {metrics.get('llm1_generation_time', '0.0')}s",
        f"Total Time: {metrics.get('llm1_total_time', '0.0')}s",
        f"Tool Called: {metrics.get('tool_called', 'None')}",
        "=========================",
        "LLM 2 (SYNTHESIS)",
        "=========================",
        f"Prompt Tokens: {metrics.get('llm2_prompt_tokens', 0)}",
        f"Completion Tokens: {metrics.get('llm2_completion_tokens', 0)}",
        f"TTFT: {metrics.get('llm2_ttft', '0.0')}s",
        f"Generation Time: {metrics.get('llm2_generation_time', '0.0')}s",
        f"Total Time: {metrics.get('llm2_total_time', '0.0')}s",
        "",
        f"User finished:               {metrics.get('timing_user_finished', 'N/A')}",
        "",
        f"Prompt assembly start:       {metrics.get('timing_prompt_assembly_start', 'N/A')}",
        f"Prompt assembly end:         {metrics.get('timing_prompt_assembly_end', 'N/A')}",
        "",
        f"LangGraph invoke:            {metrics.get('timing_langgraph_invoke', 'N/A')}",
        "",
        f"HTTP request sent:           {metrics.get('timing_http_sent', 'N/A')}",
        "",
        f"First byte from Groq:        {metrics.get('timing_first_byte', 'N/A')}",
        "",
        f"First token:                 {metrics.get('timing_first_token', 'N/A')}",
        "",
        f"Tool start:                  {metrics.get('timing_tool_start', 'N/A')}",
        f"Tool end:                    {metrics.get('timing_tool_end', 'N/A')}",
        "",
        f"Second LLM send:             {metrics.get('timing_second_llm_send', 'N/A')}",
        "",
        f"Second first token:          {metrics.get('timing_second_first_token', 'N/A')}",
        "",
        f"First text to Cartesia:      {metrics.get('timing_first_text_to_cartesia', 'N/A')}",
        "",
        f"First audio from Cartesia:   {metrics.get('timing_first_audio_from_cartesia', 'N/A')}",
        "",
        f"First packet to Twilio:      {metrics.get('timing_first_packet_to_twilio', 'N/A')}",
        "=========================\n"
    ]
    
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write("\n".join(content))
    except Exception as e:
        logger.error(f"Failed to log metrics for {session_id}: {e}")
