"""Gemini Multimodal Live API pipeline — replacing STT/LLM/TTS cascade."""

import asyncio
import base64
import json
import logging
import time
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Callable, Optional
from app.channels.base import ChannelAdapter

from google.genai import types

from app.audio_utils import build_wav, FrameGenerator, VoiceActivityDetector
from app.gemini_live_client import GeminiLiveClient
from app.logging.logger import log_pipeline_event, log_transcript, log_history

logger = logging.getLogger(__name__)

AUDIO_CACHE_DIR = Path("audio_cache")
AUDIO_CACHE_DIR.mkdir(exist_ok=True)
_DONE = object()

try:
    from langsmith.run_trees import RunTree
    from langsmith import traceable
except ImportError:
    RunTree = None
    def traceable(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper

def _safe_inputs(inputs: dict) -> dict:
    return {"session_id": inputs.get("session_id", "unknown")}

class GeminiLivePipeline:
    """
    Multimodal pipeline using Gemini Live API.
    Replaces StreamingVoicePipeline when PIPELINE_MODE=multimodal.
    """
    def __init__(self, gemini_client: GeminiLiveClient):
        self.client = gemini_client

    async def process_stream(
        self,
        audio_queue: asyncio.Queue,
        call_sid: str,
        on_tts_audio: Optional[Callable] = None,
        update_call_with_audio: bool = False,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """
        Entry point for Twilio phone calls.
        Bridges Twilio's process_stream format to the multimodal process_continuous.
        """
        _buffer = bytearray()
        
        def wrapped_tts(audio_chunk: bytes):
            if not on_tts_audio:
                return
                
            # Buffer the incoming 24kHz PCM audio from Gemini
            _buffer.extend(audio_chunk)
            
            # 24kHz, 16-bit mono = 48000 bytes/sec
            # Buffer size of 2400 bytes = 50ms of audio
            while len(_buffer) >= 2400:
                chunk = bytes(_buffer[:2400])
                del _buffer[:2400]
                
                # Wrap the 50ms chunk in a WAV header
                wav_bytes = build_wav(chunk, sample_rate=24000)
                on_tts_audio(wav_bytes)
                
        return await self.process_continuous(
            audio_queue=audio_queue,
            on_tts_audio=wrapped_tts if on_tts_audio else None,
            session_id=session_id or call_sid,
            langsmith_extra={"metadata": {"session_id": session_id or call_sid, "thread_id": session_id or call_sid}},
            **kwargs,
        )

    @traceable(run_type="chain", name="Gemini Multimodal Session", tags=["multimodal", "gemini-live"], process_inputs=_safe_inputs)
    async def process_continuous(
        self,
        audio_queue: asyncio.Queue,
        *,
        on_stt_text: Optional[Callable] = None,
        on_llm_token: Optional[Callable] = None,
        on_tts_audio: Optional[Callable] = None,
        on_stage: Optional[Callable] = None,
        on_phase_change: Optional[Callable] = None,
        on_turn_done: Optional[Callable] = None,
        session_id: Optional[str] = None,
        barge_in_event: Optional[asyncio.Event] = None,
        langsmith_extra: Optional[dict] = None,
        twilio_ws=None,
        stream_sid=None,
        **kwargs,
    ) -> dict:
        """
        Run the continuous multimodal conversation loop.
        Matches the interface of StreamingVoicePipeline.process_continuous.
        """
        resolved_session_id = session_id or f"mic-{int(time.time())}"
        turn_index = 1
        all_timings: list[dict] = []
        
        # State for tools
        state = {
            "verified": False,
            "user_name": None,
            "dob": None,
            "customer": None,
            "orders": [],
            "messages": [],
            "tool_calls": [],  # Track tool calls for transcript
        }
        
        def _set_phase(phase: str):
            if on_phase_change:
                try:
                    on_phase_change(phase)
                except Exception:
                    pass

        _set_phase("LISTENING")
        log_pipeline_event("session_start", session_id=resolved_session_id)
        
        # Connect to Gemini
        try:
            # Connect returns the async context manager
            async with self.client.connect() as session:
                logger.info(f"[{resolved_session_id}] Multimodal session started")
                
                # --- TASK 1: Sender (Read from Mic queue -> send to Gemini & local VAD) ---
                async def sender_task():
                    import os
                    use_silero = os.getenv("USE_SILERO_VAD", "true").lower() == "true"
                    silero_threshold = float(os.getenv("SILERO_THRESHOLD", "0.5"))
                    
                    vad = VoiceActivityDetector(
                        aggressiveness=3,
                        sample_rate=16000,
                        fallback_threshold=500,
                        use_silero=use_silero,
                        silero_threshold=silero_threshold,
                    )
                    frame_gen = FrameGenerator(frame_duration_ms=30, sample_rate=16000, sample_width=2)
                    
                    speech_active = False
                    consecutive_speech_ms = 0
                    consecutive_silence_ms = 0
                    vad_silence_threshold = 500  # ms to consider speech "done" to allow another barge-in
                    
                    while True:
                        try:
                            chunk = await audio_queue.get()
                            if not isinstance(chunk, bytes):
                                logger.info("Sender task received non-bytes object (_DONE)")
                                break
                            
                            # Send to Gemini
                            msg = {
                                "realtimeInput": {
                                    "audio": {
                                        "mimeType": "audio/pcm;rate=16000",
                                        "data": base64.b64encode(chunk).decode("utf-8")
                                    }
                                }
                            }
                            await session._ws.send(json.dumps(msg))
                            
                            # Local VAD logic for barge-in (requires 250ms speech debounce)
                            channel_adapter = kwargs.get("channel_adapter")
                            if channel_adapter or (twilio_ws and stream_sid):
                                frame_gen.add_data(chunk)
                                for frame in frame_gen.get_frames():
                                    is_speech = vad.is_speech(frame)
                                    if is_speech:
                                        consecutive_speech_ms += 30
                                        consecutive_silence_ms = 0
                                        if not speech_active and consecutive_speech_ms >= 250:
                                            # BARGE IN DETECTED!
                                            logger.info(f"[{resolved_session_id}] GeminiLive local VAD detected barge-in!")
                                            if channel_adapter:
                                                asyncio.create_task(channel_adapter.send_clear())
                                            else:
                                                clear_payload = {"event": "clear", "streamSid": stream_sid}
                                                asyncio.create_task(twilio_ws.send_json(clear_payload))
                                            speech_active = True
                                    else:
                                        consecutive_speech_ms = 0
                                        if speech_active:
                                            consecutive_silence_ms += 30
                                            if consecutive_silence_ms >= vad_silence_threshold:
                                                speech_active = False  # Reset so we can detect the next interruption
                            
                        except Exception as e:
                            logger.error(f"Sender task error: {e}")
                            break
                            
                # --- TASK 2: Receiver (Read from Gemini -> execute tools -> send to UI) ---
                async def receiver_task():
                    nonlocal turn_index
                    
                    turn_start_time = None
                    gemini_first_audio_ms = 0
                    current_user_text = ""
                    current_agent_text = ""
                    current_tool_summary = ""
                    output_audio_chunks = []
                    is_speaking = False
                    
                    try:
                        async def _receive_loop():
                            while True:
                                async for resp in session.receive():
                                    yield resp
                        
                        async for response in _receive_loop():
                            
                            # 1. Handle Server Content (Transcripts and Audio)
                            if response.server_content is not None:
                                
                                # A. Check for Turn Complete (End of agent's utterance)
                                if response.server_content.turn_complete:
                                    logger.info("Gemini finished turn")
                                    
                                    # Save audio cache in background
                                    if output_audio_chunks:
                                        combined_pcm = b"".join(output_audio_chunks)
                                        # Convert 24kHz PCM to WAV for saving
                                        wav_bytes = build_wav(combined_pcm, sample_rate=24000)
                                        uid = f"{resolved_session_id}-t{turn_index}"
                                        
                                        async def _save_wav(wb, u):
                                            try:
                                                fn = f"gemini_out_{u}_{int(datetime.now(UTC).timestamp())}.wav"
                                                fp = AUDIO_CACHE_DIR / fn
                                                await asyncio.to_thread(fp.write_bytes, wb)
                                            except Exception:
                                                pass
                                        asyncio.create_task(_save_wav(wav_bytes, uid))
                                        
                                    # Build agent text from tool activity if Gemini didn't send text parts
                                    if not current_agent_text and current_tool_summary:
                                        current_agent_text = current_tool_summary
                                    
                                    total_ms = gemini_first_audio_ms if gemini_first_audio_ms > 0 else 0
                                    timings = {"ttfa_total_ms": total_ms, "is_native": True}
                                    
                                    turn_result = {
                                        "intent": "multimodal",
                                        "state": "active",
                                        "verified": state["verified"],
                                        "customer": state["customer"],
                                        "orders": state["orders"],
                                        "reply_text": current_agent_text or "[audio response]",
                                        "transcript": current_user_text,
                                        "timings": timings,
                                    }
                                    all_timings.append(timings)
                                    
                                    latency_str = f"Native Audio (TTFA: {total_ms} ms)" if total_ms > 0 else "Native Audio"
                                    log_transcript(resolved_session_id, current_user_text or "[voice input]", current_agent_text or "[audio response]", latency_str)
                                    
                                    if on_turn_done:
                                        on_turn_done(turn_result)
                                    
                                    # Log to messages for history
                                    state["messages"].append({
                                        "role": "user", 
                                        "content": current_user_text or "[voice input]",
                                        "turn": turn_index,
                                    })
                                    state["messages"].append({
                                        "role": "assistant", 
                                        "content": current_agent_text or "[audio response]",
                                        "turn": turn_index,
                                        "has_audio": bool(output_audio_chunks),
                                    })
                                        
                                    _set_phase("LISTENING")
                                    is_speaking = False
                                    turn_start_time = None
                                    gemini_first_audio_ms = 0
                                    current_user_text = ""
                                    current_agent_text = ""
                                    current_tool_summary = ""
                                    output_audio_chunks.clear()
                                    turn_index += 1
                                    
                                # B. Check for Model Turn (Agent's response)
                                model_turn = response.server_content.model_turn
                                if model_turn:
                                    if not turn_start_time:
                                        # User finished speaking, agent started generating
                                        turn_start_time = time.perf_counter()
                                        _set_phase("PROCESSING")
                                        
                                    for part in model_turn.parts:
                                        # Handle Text Transcription (LLM output)
                                        if part.text:
                                            current_agent_text += part.text
                                            if on_llm_token:
                                                on_llm_token(part.text)
                                                
                                        # Handle Audio Data (TTS output)
                                        if part.inline_data:
                                            if not is_speaking:
                                                # First audio byte arrived
                                                gemini_first_audio_ms = (time.perf_counter() - turn_start_time) * 1000
                                                is_speaking = True
                                                _set_phase("SPEAKING")
                                                
                                            audio_chunk = part.inline_data.data
                                            output_audio_chunks.append(audio_chunk)
                                            if on_tts_audio:
                                                # Gemini sends 24kHz raw PCM.
                                                # We send the raw PCM so the frontend can decode it natively without WAV headers.
                                                on_tts_audio(audio_chunk)
                                                
                            # 2. Handle Tool Calls
                            if response.tool_call is not None:
                                for fc in response.tool_call.function_calls:
                                    if on_stage:
                                        on_stage("conversation", "running", f"Gemini executing tool: {fc.name}")
                                        
                                    # Execute the tool
                                    tool_response = await self.client.execute_tool_call(
                                        tool_call_id=fc.id,
                                        name=fc.name,
                                        args=fc.args,
                                        state=state
                                    )
                                    
                                    # Build a text summary of the tool call for transcripts
                                    tool_info = f"[Tool: {fc.name}({fc.args})]"
                                    if hasattr(tool_response, 'response') and tool_response.response:
                                        tool_info += f" -> {tool_response.response}"
                                    current_tool_summary += tool_info + " "
                                    state["tool_calls"].append({
                                        "name": fc.name,
                                        "args": fc.args,
                                        "turn": turn_index,
                                    })
                                    
                                    if on_stage:
                                        on_stage("conversation", "done", f"Tool {fc.name} complete")
                                        
                                    # Send response back to Gemini session
                                    await session.send(input=tool_response)
                                    
                    except asyncio.CancelledError:
                        logger.info("Receiver task cancelled")
                    except Exception as e:
                        logger.error(f"Receiver task error: {e}")
                        
                # Start sender and receiver concurrently
                sender = asyncio.create_task(sender_task())
                receiver = asyncio.create_task(receiver_task())
                
                # If a barge-in event is triggered, we can't easily interrupt Gemini's current WSS stream
                # without cancelling the session. But we can monitor the queue closure.
                await asyncio.gather(sender, receiver)
                
        except Exception as e:
            logger.error(f"Multimodal pipeline failed: {e}")
        finally:
            _set_phase("IDLE")
            log_pipeline_event("session_end", session_id=resolved_session_id, total_turns=turn_index)
            
            # Save final history
            log_history(resolved_session_id, state)
            
            return {"total_turns": turn_index, "state": state}
