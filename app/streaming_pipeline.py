"""
Streaming voice pipeline — continuous conversational turn-taking.

Upgraded from single-utterance to multi-turn continuous pipeline:
  - Continuous VAD-based utterance detection
  - Automatic endpointing via configurable silence thresholds
  - Turn-taking loop: listen → detect → STT → LLM → TTS → speak → listen
  - Barge-in detection (speech during TTS playback)

The pipeline keeps running until the session ends or the WebSocket closes.
Each detected utterance spawns the STT → LLM → TTS workers for that turn.
"""

import asyncio
import io
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from app.audio_utils import (
    build_wav,
    mulaw_to_pcm,
    resample_to_16khz,
    detect_silence,
    trim_trailing_silence,
    compute_rms,
    VoiceActivityDetector,
    FrameGenerator,
)
from app.database import DatabaseClient
from app.groq_client import GroqClient
from app.llm.rephrase import LLMRephraser
from app.services.agent_service import AgentService
from app.logging.logger import log_event, log_pipeline_event, log_transcript
from app.response_cache import ResponseCache
from app.twilio_handler import TwilioHandler

logger = logging.getLogger(__name__)

# --- Environment Variables ---
MAX_UTTERANCE_MS = int(os.getenv("MAX_UTTERANCE_MS", "30000"))
SILENCE_DURATION_MS = int(os.getenv("SILENCE_DURATION_MS", "1500"))
VAD_SILENCE_MS = int(os.getenv("VAD_SILENCE_MS", "800"))
SILENCE_THRESHOLD = int(os.getenv("SILENCE_THRESHOLD", "500"))
TTS_CACHE_SIZE = int(os.getenv("TTS_CACHE_SIZE", "100"))
STT_EARLY_CHUNK_SECONDS = float(os.getenv("STT_EARLY_CHUNK_SECONDS", "1.0"))
MIN_SPEECH_MS = int(os.getenv("MIN_SPEECH_MS", "200"))
SERVER_HOST = os.getenv("SERVER_HOST", "http://localhost:8000")
VAD_AGGRESSIVENESS = int(os.getenv("VAD_AGGRESSIVENESS", "3"))
USE_SILERO_VAD = os.getenv("USE_SILERO_VAD", "false").lower() in ("1", "true", "yes", "on")
SILERO_THRESHOLD = float(os.getenv("SILERO_THRESHOLD", "0.5"))

USE_FILLER_WORDS = os.getenv("USE_FILLER_WORDS", "true").lower() in ("1", "true", "yes", "on")

# Audio cache directory
AUDIO_CACHE_DIR = Path("audio_cache")
AUDIO_CACHE_DIR.mkdir(exist_ok=True)

# Sentinel to signal a queue that no more items are coming
_DONE = object()


class ConversationPhase(str, Enum):
    """Real-time conversation phase for the streaming room."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    SPEECH_DETECTED = "SPEECH_DETECTED"
    ENDPOINTING = "ENDPOINTING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    ENDED = "ENDED"


class StreamingVoicePipeline:
    """
    Concurrent streaming pipeline with continuous turn-taking.

    Modes:
      - Single-turn (legacy): process_stream() processes one utterance
      - Multi-turn (new): process_continuous() runs a conversation loop
    """

    SYSTEM_PROMPT = (
        "You are a helpful, friendly customer support voice agent. "
        "Assist callers with order status and general questions. "
        "Keep responses to 1-2 sentences since they'll be spoken aloud. "
        "Be warm, professional, direct. No markdown or formatting."
    )

    def __init__(
        self,
        groq_client: GroqClient,
        db_client: DatabaseClient,
        twilio_handler: TwilioHandler,
        agent_service: AgentService,
        rephraser: LLMRephraser,
        cartesia_client = None,
    ):
        self.groq = groq_client
        self.cartesia = cartesia_client
        self.tts_provider = os.getenv("TTS_PROVIDER", "groq").lower()
        self.db = db_client
        self.twilio = twilio_handler
        self.tts_cache = ResponseCache(max_size=TTS_CACHE_SIZE)
        self.agent = agent_service
        self.rephraser = rephraser
        self._current_phase = None

        self.stt_provider = os.getenv("STT_PROVIDER", "groq").lower()
        if self.stt_provider == "deepgram":
            from app.stt.deepgram_client import DeepgramStreamingClient
            dg_key = os.getenv("DEEPGRAM_API_KEY", "")
            self.deepgram = DeepgramStreamingClient(dg_key) if dg_key else None
        else:
            self.deepgram = None



        # Filler words manager
        from app.fillers import FillerManager
        self._fillers = FillerManager() if USE_FILLER_WORDS else None

    # =====================================================================
    #  NEW: Continuous conversation loop (multi-turn)
    # =====================================================================
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
        **kwargs,
    ) -> dict:
        cartesia_ws = None
        if self.tts_provider == "cartesia" and self.cartesia:
            cartesia_ws = await self.cartesia.client.tts.websocket()
            await cartesia_ws.connect()
            kwargs["cartesia_ws"] = cartesia_ws

        if self.deepgram:
            await self.deepgram.connect()
        try:
            return await self._process_continuous_internal(
                audio_queue=audio_queue,
                on_stt_text=on_stt_text,
                on_llm_token=on_llm_token,
                on_tts_audio=on_tts_audio,
                on_stage=on_stage,
                on_phase_change=on_phase_change,
                on_turn_done=on_turn_done,
                session_id=session_id,
                barge_in_event=barge_in_event,
                **kwargs,
            )
        finally:
            if self.deepgram:
                await self.deepgram.close()
            if cartesia_ws:
                await cartesia_ws.close()

    async def _process_continuous_internal(
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
        **kwargs,
    ) -> dict:
        """
        Run a continuous conversation loop with VAD-based turn detection.

        The loop:
          1. Listen for audio, detect speech via VAD
          2. When silence threshold is reached, finalize utterance
          3. Run STT → LLM → TTS for the utterance
          4. Signal TTS playback to frontend
          5. Resume listening

        Args:
            audio_queue: Continuous stream of raw PCM audio chunks (bytes).
                         Producer puts _DONE when the session ends.
            on_stt_text: Callback(text: str) — transcript updates.
            on_llm_token: Callback(token: str) — LLM token streaming.
            on_tts_audio: Callback(audio_bytes: bytes) — TTS audio chunks.
            on_stage: Callback(stage, status, detail) — pipeline stage updates.
            on_phase_change: Callback(phase: str) — conversation phase changes.
            on_turn_done: Callback(result: dict) — called after each turn.
            session_id: Session identifier.
            barge_in_event: asyncio.Event set when user interrupts TTS playback.

        Returns:
            Final session summary dict.
        """
        resolved_session_id = session_id or str(uuid.uuid4())[:8]
        turn_index = 0
        session_ended = False
        all_timings: list[dict] = []

        def _set_phase(phase):
            val = phase.value if hasattr(phase, 'value') else phase
            self._current_phase = val
            if on_phase_change:
                try:
                    on_phase_change(val)
                except Exception:
                    pass

        _set_phase(ConversationPhase.LISTENING)
        log_pipeline_event("session_start", session_id=resolved_session_id)

        # We start with listening for the first utterance
        _set_phase(ConversationPhase.LISTENING)
        utterance_data = await self._vad_collect_utterance(
            audio_queue,
            session_id=resolved_session_id,
            utterance_id=f"{resolved_session_id}-t0",
            on_phase_change=_set_phase,
            on_stage=on_stage,
        )

        while not session_ended:
            if not utterance_data:
                break
                
            utterance_audio, vad_done_reason, vad_speech_ms, vad_silence_ms = utterance_data
            dg_task = None

            if vad_done_reason == "stream_ended":
                log_pipeline_event(
                    "stream_ended",
                    session_id=resolved_session_id,
                    utterance_id=f"{resolved_session_id}-end",
                    turn_index=turn_index,
                )
                session_ended = True
                if not utterance_audio or len(utterance_audio) < 3200:
                    break

            if not utterance_audio or len(utterance_audio) < 3200:
                # Not enough audio for a real utterance, keep listening
                log_pipeline_event(
                    "utterance_too_short",
                    session_id=resolved_session_id,
                    utterance_id=f"{resolved_session_id}-short",
                    turn_index=turn_index,
                    bytes=len(utterance_audio) if utterance_audio else 0,
                )
                if session_ended:
                    break
                # Fetch next utterance directly
                utterance_data = await self._vad_collect_utterance(
                    audio_queue,
                    session_id=resolved_session_id,
                    utterance_id=f"{resolved_session_id}-t{turn_index}",
                    on_phase_change=_set_phase,
                    on_stage=on_stage,
                )
                continue

            # We have a valid utterance. Advance the turn index.
            turn_index += 1
            utterance_id = f"{resolved_session_id}-t{turn_index}"
            
            log_pipeline_event(
                "turn_start",
                session_id=resolved_session_id,
                utterance_id=utterance_id,
                turn_index=turn_index,
            )

            # ----- Step 2: Process the utterance (STT → LLM → TTS) -----
            _set_phase(ConversationPhase.PROCESSING)
            log_pipeline_event(
                "utterance_finalized",
                session_id=resolved_session_id,
                utterance_id=utterance_id,
                turn_index=turn_index,
                audio_bytes=len(utterance_audio),
            )

            # Create the processing task
            process_task = asyncio.create_task(
                self._process_single_utterance(
                    utterance_audio,
                    session_id=resolved_session_id,
                    utterance_id=utterance_id,
                    turn_index=turn_index,
                    speech_ms=vad_speech_ms,
                    vad_silence_ms=vad_silence_ms,
                    dg_task=dg_task,
                    on_stt_text=on_stt_text,
                    on_llm_token=on_llm_token,
                    on_tts_audio=on_tts_audio,
                    on_stage=on_stage,
                    on_phase_change=_set_phase,
                    cartesia_ws=kwargs.get("cartesia_ws"),
                )
            )

            # ----- Step 3: Listen for interruption concurrently -----
            interruption_event = asyncio.Event()
            vad_task = asyncio.create_task(
                self._vad_collect_utterance(
                    audio_queue,
                    session_id=resolved_session_id,
                    utterance_id=f"{resolved_session_id}-t{turn_index+1}",
                    on_phase_change=_set_phase,
                    on_stage=on_stage,
                    interruption_event=interruption_event,
                )
            )

            waiters = [process_task, asyncio.create_task(interruption_event.wait())]
            if barge_in_event:
                waiters.append(asyncio.create_task(barge_in_event.wait()))

            # Wait for either processing to finish OR an interruption
            done, pending = await asyncio.wait(
                waiters, 
                return_when=asyncio.FIRST_COMPLETED
            )

            interrupted = False
            for task in done:
                # If either interruption event was set, we have a barge-in
                if task is not process_task:
                    interrupted = True

            if interrupted:
                log_pipeline_event(
                    "barge_in_detected",
                    session_id=resolved_session_id,
                    utterance_id=utterance_id,
                    turn_index=turn_index,
                )
                
                # Cancel the currently processing/speaking turn
                process_task.cancel()
                try:
                    await process_task
                except asyncio.CancelledError:
                    pass

                if barge_in_event and barge_in_event.is_set():
                    barge_in_event.clear()

                _set_phase(ConversationPhase.INTERRUPTED)
                
                # Wait for the VAD task to finish collecting the new interrupting utterance
                utterance_data = await vad_task

            else:
                # Processing finished normally without interruption
                turn_result = process_task.result()
                
                all_timings.append(turn_result.get("timings", {}))

                if on_turn_done:
                    try:
                        on_turn_done(turn_result)
                    except Exception:
                        pass

                # Check if the conversation should end
                if turn_result.get("should_end", False):
                    session_ended = True
                    _set_phase(ConversationPhase.ENDED)
                    log_pipeline_event(
                        "session_end_by_intent",
                        session_id=resolved_session_id,
                        turn_index=turn_index,
                    )
                    # We can cancel the waiting vad task since we're ending
                    vad_task.cancel()
                    break
                    
                _set_phase(ConversationPhase.LISTENING)
                log_pipeline_event(
                    "turn_complete",
                    session_id=resolved_session_id,
                    utterance_id=utterance_id,
                    turn_index=turn_index,
                    timings=turn_result.get("timings", {}),
                )
                
                # Now wait for the user's next utterance (the VAD task is already running and waiting)
                utterance_data = await vad_task

        _set_phase(ConversationPhase.ENDED)
        log_pipeline_event(
            "session_end",
            session_id=resolved_session_id,
            total_turns=turn_index,
        )

        return {
            "session_id": resolved_session_id,
            "total_turns": turn_index,
            "all_timings": all_timings,
        }

    # =====================================================================
    #  VAD: Collect one utterance from continuous audio stream
    # =====================================================================
    async def _vad_collect_utterance(
        self,
        audio_queue: asyncio.Queue,
        *,
        session_id: str,
        utterance_id: str,
        on_phase_change: Optional[Callable] = None,
        on_stage: Optional[Callable] = None,
        interruption_event: Optional[asyncio.Event] = None,
    ) -> tuple[Optional[bytes], str, float, float]:
        """
        Listen to the audio_queue and collect frames for one utterance.

        Uses WebRTC VAD (via VoiceActivityDetector):
        1. Wait for speech to start (frames where VAD is true)
        2. Once speech starts, buffer all frames
        3. When silence exceeds VAD_SILENCE_MS, finalize the utterance

        Returns:
            (utterance_pcm_bytes, reason, speech_ms, silence_ms)
            reason is one of: "silence", "max_duration", "stream_ended"
            speech_ms is the total milliseconds of detected speech energy
            silence_ms is the actual silence duration that triggered endpointing
        """
        audio_buffer = bytearray()
        speech_started = False
        silence_ms = 0.0
        speech_ms = 0.0
        t_start = time.perf_counter()
        last_vad_log = t_start
        


        # Configuration
        vad_silence_ms = max(1, VAD_SILENCE_MS)
        min_speech_ms = max(1, MIN_SPEECH_MS)
        sample_rate = 16000
        sample_width = 2
        # Max utterance in bytes (16kHz, 16-bit mono = 32000 bytes/sec)
        max_utterance_bytes = int(MAX_UTTERANCE_MS / 1000 * 16000 * 2)

        # WebRTC VAD works on exact 30ms frames
        frame_gen = FrameGenerator(frame_duration_ms=30, sample_rate=sample_rate, sample_width=sample_width)
        vad = VoiceActivityDetector(
            aggressiveness=VAD_AGGRESSIVENESS,
            sample_rate=sample_rate,
            fallback_threshold=SILENCE_THRESHOLD,
            use_silero=USE_SILERO_VAD,
            silero_threshold=SILERO_THRESHOLD,
        )

        if on_stage:
            try:
                on_stage("vad", "running", "Listening for speech…")
            except Exception:
                pass

        while True:
            try:
                # Use a timeout so we don't block forever if audio stops
                item = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                # No audio for 500ms — if we have speech already, maybe finalize
                if speech_started and len(audio_buffer) > 0:
                    silence_ms += 500
                    if silence_ms >= vad_silence_ms:
                        return bytes(audio_buffer), "silence", speech_ms, silence_ms
                continue

            if item is _DONE:
                # Stream ended
                if speech_started and audio_buffer:
                    return bytes(audio_buffer), "stream_ended", speech_ms, silence_ms
                return None, "stream_ended", 0.0, 0.0

            chunk = bytes(item)
            frame_gen.add_data(chunk)

            for frame in frame_gen.get_frames():
                chunk_ms = frame_gen.frame_duration_ms
                rms = compute_rms(frame, sample_width=sample_width)

                # WebRTC VAD checks if frame is speech
                is_speech_frame = vad.is_speech(frame)
                is_silence = not is_speech_frame

                if not speech_started:
                    if not is_silence:
                        speech_started = True
                        speech_ms = chunk_ms
                        silence_ms = 0.0
                        audio_buffer.extend(frame)
                        
                        if self.deepgram:
                            self.deepgram.clear_buffer()
                            await self.deepgram.send_audio(bytes(audio_buffer))
                        
                        if interruption_event:
                            interruption_event.set()
                        if on_phase_change:
                            on_phase_change(ConversationPhase.SPEECH_DETECTED.value)
                        log_pipeline_event(
                            "speech_detected",
                            session_id=session_id,
                            utterance_id=utterance_id,
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 1),
                        )
                        if on_stage:
                            try:
                                on_stage("vad", "running", "Speech detected")
                            except Exception:
                                pass
                    # else: still silence before speech, discard
                else:
                    audio_buffer.extend(frame)
                    if self.deepgram:
                        await self.deepgram.send_audio(bytes(frame))

                    if is_silence:
                        silence_ms += chunk_ms
                    else:
                        silence_ms = 0.0
                        speech_ms += chunk_ms

                    now = time.perf_counter()
                    if now - last_vad_log >= 1.0:
                        log_pipeline_event(
                            "vad_chunk",
                            session_id=session_id,
                            utterance_id=utterance_id,
                            rms=rms,
                            chunk_ms=round(chunk_ms, 1),
                            is_silence=is_silence,
                            speech_started=speech_started,
                            speech_ms=round(speech_ms, 1),
                            silence_ms=round(silence_ms, 1),
                        )
                        last_vad_log = now

                    # Check endpointing: enough silence after speech
                    if silence_ms >= vad_silence_ms:
                        if speech_ms >= min_speech_ms:
                            if on_phase_change:
                                on_phase_change(ConversationPhase.ENDPOINTING.value)
                            log_pipeline_event(
                                "silence_endpointing",
                                session_id=session_id,
                                utterance_id=utterance_id,
                                silence_ms=round(silence_ms, 1),
                                speech_ms=round(speech_ms, 1),
                            )
                            if on_stage:
                                try:
                                    on_stage("vad", "done", f"Utterance finalized (silence: {round(silence_ms)}ms)")
                                except Exception:
                                    pass
                            
                            # Grab any remaining partial frame data in buffer
                            if len(frame_gen.buffer) > 0:
                                audio_buffer.extend(frame_gen.buffer)
                                if self.deepgram: await self.deepgram.send_audio(bytes(frame_gen.buffer))
                                
                            return bytes(audio_buffer), "silence", speech_ms, silence_ms
                        else:
                            # False alarm (short click/pop), reset VAD state
                            if self.deepgram:
                                _ = await self.deepgram.get_transcript()
                            speech_started = False
                            speech_ms = 0.0
                            silence_ms = 0.0
                            audio_buffer.clear()
                            if on_phase_change:
                                on_phase_change(ConversationPhase.LISTENING.value)
                            if on_stage:
                                try:
                                    on_stage("vad", "running", "Listening for speech…")
                                except Exception:
                                    pass

                    # Check max utterance duration
                    if len(audio_buffer) >= max_utterance_bytes:
                        log_pipeline_event(
                            "max_utterance_reached",
                            session_id=session_id,
                            utterance_id=utterance_id,
                            duration_ms=MAX_UTTERANCE_MS,
                        )
                        if on_stage:
                            try:
                                on_stage("vad", "done", "Max utterance duration reached")
                            except Exception:
                                pass
                        
                        if len(frame_gen.buffer) > 0:
                            audio_buffer.extend(frame_gen.buffer)
                            if self.deepgram: await self.deepgram.send_audio(bytes(frame_gen.buffer))
                            
                        return bytes(audio_buffer), "max_duration", speech_ms, silence_ms

    # =====================================================================
    #  Process a single utterance through STT → LLM → TTS
    # =====================================================================
    async def _process_single_utterance(
        self,
        utterance_pcm: bytes,
        *,
        session_id: str,
        utterance_id: str,
        turn_index: int,
        speech_ms: float = 0.0,
        vad_silence_ms: float = 0.0,
        dg_task: Optional[asyncio.Task] = None,
        on_stt_text: Optional[Callable] = None,
        on_llm_token: Optional[Callable] = None,
        on_tts_audio: Optional[Callable] = None,
        on_stage: Optional[Callable] = None,
        on_phase_change: Optional[Callable] = None,
        cartesia_ws: Optional[Any] = None,
    ) -> dict:
        """
        Process a single finalized utterance through the full pipeline.

        Runs STT → Conversation Service → (optional LLM rephrase) → TTS.
        Returns a result dict with transcript, intent, reply, timings, etc.
        """
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        result: dict[str, Any] = {
            "session_id": session_id,
            "utterance_id": utterance_id,
            "turn_index": turn_index,
            "transcript": "",
            "intent": "unknown",
            "customer": None,
            "orders": [],
            "reply_text": "",
            "audio_bytes": b"",
            "audio_url": "",
            "audio_path": "",
            "state": "",
            "verified": False,
            "should_end": False,
            "stages": [],
            "timings": timings,
        }

        def _stage(name: str, status: str, detail: str = ""):
            result["stages"].append({
                "stage": name, "status": status,
                "detail": detail, "ts": datetime.now(UTC).isoformat(),
            })
            if on_stage:
                try:
                    on_stage(name, status, detail)
                except Exception:
                    pass

        try:
            # ------ STT ------
            _stage("stt", "running", "Transcribing utterance…")
            timings["stt_start"] = round(time.perf_counter() - t0, 4)

            # For Deepgram streaming STT, skip heavy audio processing — Deepgram already has the audio.
            # Only build WAV for Groq Whisper fallback (which needs a file upload).
            if self.stt_provider == "deepgram" and self.deepgram:
                # Save input audio in background (non-blocking) for debugging only
                async def _save_input_audio_bg(pcm, uid):
                    try:
                        wav = build_wav(pcm, sample_rate=16000)
                        fn = f"input_{uid}_{int(datetime.now(UTC).timestamp())}.wav"
                        fp = AUDIO_CACHE_DIR / fn
                        await asyncio.to_thread(fp.write_bytes, wav)
                        result["input_audio_url"] = f"{SERVER_HOST}/audio/{fn}"
                    except Exception as e:
                        logger.debug(f"Background audio save failed: {e}")
                asyncio.create_task(_save_input_audio_bg(utterance_pcm, utterance_id))
            else:
                trimmed_pcm = trim_trailing_silence(utterance_pcm)
                wav_bytes = build_wav(trimmed_pcm, sample_rate=16000)
                # Save input audio in background
                async def _save_input_wav_bg(wb, uid):
                    try:
                        fn = f"input_{uid}_{int(datetime.now(UTC).timestamp())}.wav"
                        fp = AUDIO_CACHE_DIR / fn
                        await asyncio.to_thread(fp.write_bytes, wb)
                        result["input_audio_url"] = f"{SERVER_HOST}/audio/{fn}"
                    except Exception as e:
                        logger.debug(f"Background audio save failed: {e}")
                asyncio.create_task(_save_input_wav_bg(wav_bytes, utterance_id))

            stt_engine_used = self.stt_provider
            try:
                if self.stt_provider == "deepgram" and self.deepgram:
                    transcript = await self.deepgram.get_transcript()
                else:
                    transcript = await self.groq.speech_to_text(wav_bytes, ext="wav")

                timings["stt_end"] = round(time.perf_counter() - t0, 4)
                timings["stt_duration"] = round(timings["stt_end"] - timings["stt_start"], 4)
                result["transcript"] = transcript
                _stage("stt", "done", f"[{stt_engine_used}] {transcript}")
                logger.info(f"[{utterance_id}] STT ({stt_engine_used}): '{transcript}'")

                log_pipeline_event(
                    "stt_complete",
                    session_id=session_id,
                    utterance_id=utterance_id,
                    turn_index=turn_index,
                    duration_ms=timings["stt_duration"] * 1000,
                    transcript=transcript[:100],
                    engine=stt_engine_used,
                )

                if on_stt_text:
                    try:
                        on_stt_text(transcript)
                    except Exception:
                        pass

                # ------ Send filler word while processing ------
                if self._fillers and transcript and transcript.strip():
                    filler_phrase = self._fillers.get_filler_for_turn(turn_index)
                    if filler_phrase and on_tts_audio:
                        try:
                            filler_audio = self.tts_cache.get(filler_phrase)
                            if not filler_audio:
                                if self.tts_provider == "cartesia" and self.cartesia:
                                    filler_audio = await self.cartesia.text_to_speech(filler_phrase)
                                else:
                                    filler_audio = await self.groq.text_to_speech(filler_phrase)
                                self.tts_cache.put(filler_phrase, filler_audio)
                            if filler_audio:
                                on_tts_audio(filler_audio)
                                if "tts_first_audio" not in timings:
                                    timings["tts_first_audio"] = round(time.perf_counter() - t0, 4)
                                logger.info(f"[{utterance_id}] Filler sent: '{filler_phrase}'")
                        except Exception as filler_err:
                            logger.warning(f"Filler TTS failed: {filler_err}")

            except Exception as e:
                logger.error(f"[{utterance_id}] STT failed: {e}")
                _stage("stt", "failed", str(e))
                timings["stt_end"] = round(time.perf_counter() - t0, 4)
                result["reply_text"] = "I'm sorry, I couldn't understand that. Could you repeat?"
                return result

            cleaned_transcript = transcript.strip().lower()

            # --- Pure Whisper artifacts (always discard) ---
            whisper_artifacts = {
                ".", ",", "!", "?",
                "you.", "you",
                "you're welcome.", "you're welcome", "welcome.", "welcome",
                "test.", "test", "am i?", "am i", "is it?", "is it",
                "i", "i.", "my...", "my",
                "goodbye.", "goodbye", "good bye.", "good bye",
            }

            if not transcript or not transcript.strip():
                _stage("stt", "done", "No speech detected")
                result["reply_text"] = ""
                return result

            if cleaned_transcript in whisper_artifacts:
                _stage("stt", "done", f"Whisper artifact suppressed: '{cleaned_transcript}'")
                log_pipeline_event(
                    "turn_route", route="whisper_artifact_suppressed",
                    session_id=session_id, utterance_id=utterance_id,
                    transcript=cleaned_transcript,
                )
                result["reply_text"] = ""
                return result

            # --- Energy-based noise hallucination check ---
            # If speech energy was very short AND the transcript is a single
            # very short word, it's almost certainly noise that Whisper decoded.
            # Adjusted for WebRTC VAD: shorter utterances like "yes" can be ~150ms.
            word_count = len(cleaned_transcript.split())
            is_very_short_audio = speech_ms > 0 and speech_ms < 150
            is_tiny_transcript = word_count <= 2 and len(cleaned_transcript) <= 8

            if is_very_short_audio and is_tiny_transcript:
                _stage("stt", "done", f"Noise hallucination suppressed (speech_ms={round(speech_ms)}ms): '{cleaned_transcript}'")
                log_pipeline_event(
                    "turn_route", route="noise_hallucination_suppressed",
                    session_id=session_id, utterance_id=utterance_id,
                    transcript=cleaned_transcript, speech_ms=round(speech_ms, 1),
                )
                result["reply_text"] = ""
                return result

            # ------ Conversation Service (intent + verification + DB) ------
            _stage("conversation", "running", "Routing intent and slots")
            timings["conversation_start"] = round(time.perf_counter() - t0, 4)

            tts_queue = asyncio.Queue()
            token_buffer = []
            
            # Decide if we stream TTS directly from LangGraph (only if not rephrasing)
            stream_direct = not (self.rephraser and self.rephraser.enabled)

            def _handle_llm_token(token: str):
                if on_llm_token:
                    try:
                        on_llm_token(token)
                    except Exception:
                        pass
                
                if stream_direct:
                    token_buffer.append(token)
                    current_text = "".join(token_buffer)
                    sentences = _split_sentences(current_text)
                    if len(sentences) > 1:
                        for sentence in sentences[:-1]:
                            s = sentence.strip()
                            if s:
                                tts_queue.put_nowait(s)
                        token_buffer.clear()
                        token_buffer.append(sentences[-1])

            async def _tts_consumer():
                while True:
                    sentence = await tts_queue.get()
                    if sentence is None:
                        break
                    await self._tts_sentence(sentence, result, timings, t0, _stage, on_tts_audio, cartesia_ws=cartesia_ws)
                    tts_queue.task_done()

            tts_consumer_task = None
            if stream_direct:
                tts_consumer_task = asyncio.create_task(_tts_consumer())

            try:
                conversation = await self.agent.handle_user_text(session_id, transcript, on_llm_token=_handle_llm_token)
                
                if stream_direct:
                    remaining = "".join(token_buffer).strip()
                    if remaining:
                        tts_queue.put_nowait(remaining)
                    tts_queue.put_nowait(None)
                
                result["intent"] = conversation.intent
                result["reply_text"] = conversation.reply_text
                result["state"] = conversation.state
                result["verified"] = conversation.verified
                result["customer"] = _serialize_customer(conversation.customer)
                result["orders"] = conversation.orders
                result["should_end"] = conversation.should_end
                timings.update(conversation.timings)
                
                # Record conversation duration BEFORE awaiting TTS to prevent audio generation time from inflating LLM time
                timings["conversation_end"] = round(time.perf_counter() - t0, 4)
                timings["conversation_duration"] = round(
                    timings["conversation_end"] - timings["conversation_start"], 4
                )
                
                if stream_direct:
                    await tts_consumer_task
                _stage("conversation", "done", f"intent={conversation.intent}, state={conversation.state}")

                log_pipeline_event(
                    "conversation_complete",
                    session_id=session_id,
                    utterance_id=utterance_id,
                    turn_index=turn_index,
                    intent=conversation.intent,
                    state=conversation.state,
                    duration_ms=timings["conversation_duration"] * 1000,
                )
            except Exception as e:
                logger.exception(f"[{utterance_id}] Conversation service error: {e}")
                _stage("conversation", "failed", str(e))
                if stream_direct:
                    tts_queue.put_nowait(None)
                    await tts_consumer_task
                result["reply_text"] = "I'm sorry, something went wrong. Please try again."
            finally:
                if tts_consumer_task and not tts_consumer_task.done():
                    tts_consumer_task.cancel()
                    try:
                        await tts_consumer_task
                    except asyncio.CancelledError:
                        pass
                timings["conversation_end"] = round(time.perf_counter() - t0, 4)

            reply_text = result["reply_text"]
            if not reply_text:
                reply_text = "I'm sorry, I couldn't process that. Please try again."
                result["reply_text"] = reply_text

            # ------ Optional LLM Rephrase ------
            if self.rephraser and self.rephraser.enabled:
                _stage("llm", "running", "Rephrasing response…")
                timings["llm_start"] = round(time.perf_counter() - t0, 4)
                first_token_received = False
                token_buffer = []
                full_reply_parts = []

                try:
                    async for token in self.rephraser.stream_rephrase(reply_text):
                        if not first_token_received:
                            timings["llm_first_token"] = round(time.perf_counter() - t0, 4)
                            first_token_received = True

                        token_buffer.append(token)
                        full_reply_parts.append(token)

                        if on_llm_token:
                            try:
                                on_llm_token(token)
                            except Exception:
                                pass

                        current_text = "".join(token_buffer)
                        sentences = _split_sentences(current_text)

                        if len(sentences) > 1:
                            for sentence in sentences[:-1]:
                                sentence = sentence.strip()
                                if sentence:
                                    # TTS each sentence as it completes
                                    await self._tts_sentence(
                                        sentence, result, timings, t0, _stage, on_tts_audio, cartesia_ws=cartesia_ws
                                    )
                            token_buffer = [sentences[-1]]

                    remaining = "".join(token_buffer).strip()
                    if remaining:
                        await self._tts_sentence(
                            remaining, result, timings, t0, _stage, on_tts_audio, cartesia_ws=cartesia_ws
                        )

                    full_reply = "".join(full_reply_parts).strip()
                    result["reply_text"] = full_reply or reply_text
                    timings["llm_end"] = round(time.perf_counter() - t0, 4)
                    _stage("llm", "done", result["reply_text"][:80])

                except Exception as e:
                    logger.error(f"[{utterance_id}] LLM rephrase failed: {e}")
                    _stage("llm", "failed", "Rephrase failed — using original")
                    for sentence in _split_sentences(reply_text):
                        if sentence.strip():
                            await self._tts_sentence(
                                sentence.strip(), result, timings, t0, _stage, on_tts_audio, cartesia_ws=cartesia_ws
                            )
            elif not stream_direct:
                _stage("llm", "done", "Deterministic response")
                # Pipelined TTS: Split reply into sentences and synthesize sequentially
                for sentence in _split_sentences(reply_text):
                    if sentence.strip():
                        await self._tts_sentence(
                            sentence.strip(), result, timings, t0, _stage, on_tts_audio, cartesia_ws=cartesia_ws
                        )
            else:
                _stage("llm", "done", "Streamed direct response")

            if on_phase_change:
                on_phase_change(ConversationPhase.SPEAKING.value)

            # Save combined output audio to cache (background — non-blocking)
            combined_audio = result.get("audio_bytes")
            if combined_audio:
                filename = f"output_{utterance_id}_{int(datetime.now(UTC).timestamp())}.wav"
                filepath = AUDIO_CACHE_DIR / filename
                audio_url = f"{SERVER_HOST}/audio/{filename}"
                result["audio_url"] = audio_url
                result["audio_path"] = str(filepath)
                async def _save_output_bg(fp, data):
                    try:
                        await asyncio.to_thread(fp.write_bytes, data)
                        logger.info(f"[{utterance_id}] Output audio saved: {fp} ({len(data)} bytes)")
                    except Exception as e:
                        logger.debug(f"Background output save failed: {e}")
                asyncio.create_task(_save_output_bg(filepath, combined_audio))

            # ── Correct TTFA (Time To First Audio) calculation ──
            # 
            # The user's perceived latency is:
            #   TTFA = VAD silence wait + time from processing start to first audio byte
            #
            # t0 is set at the START of _process_single_utterance (after VAD finishes).
            # tts_first_audio is measured relative to t0, so it already includes:
            #   STT flush + LLM-to-first-sentence + TTS-to-first-chunk
            # These overlap partially (Deepgram streams while speaking, TTS starts
            # before LLM finishes), so summing individual durations would OVERCOUNT.
            #
            # For the BREAKDOWN, we show non-overlapping segments:
            #   STT: stt_duration (time to get transcript after VAD)
            #   LLM: time from stt_end to tts_start (LLM processing until first sentence)  
            #   TTS: tts_first_audio - tts_start (Cartesia processing for first sentence)
            
            # Use actual VAD silence from the endpointing detector, not the env config
            vad_wait = vad_silence_ms  # actual measured silence, not the configured threshold
            
            stt_ms = timings.get("stt_duration", 0.0) * 1000
            
            # LLM latency = time from STT completion to when TTS starts on the first sentence
            # This captures the actual LLM processing time (including tool calls, multi-LLM)
            stt_end = timings.get("stt_end", 0.0)
            tts_start = timings.get("tts_start", 0.0)
            if tts_start and stt_end:
                llm_ms = (tts_start - stt_end) * 1000
            else:
                llm_ms = timings.get("conversation_duration", 0.0) * 1000
            
            # TTS latency = time from TTS start to first audio chunk
            tts_first = timings.get("tts_first_audio", timings.get("tts_end", timings.get("total", 0.0)))
            tts_ms = (tts_first - tts_start) * 1000 if tts_start else 0.0
            
            # Total TTFA = VAD silence + tts_first_audio (which includes STT + LLM + TTS from t0)
            # This is the TRUE wall-clock latency the user perceives
            tts_first_from_t0 = timings.get("tts_first_audio", timings.get("total", 0.0))
            total_ms = vad_wait + (tts_first_from_t0 * 1000)
            
            # Inject exact TTFA calculations into timings for the frontend UI
            timings["vad_wait_ms"] = vad_wait
            timings["stt_ms"] = stt_ms
            timings["llm_ms"] = llm_ms
            timings["tts_first_ms"] = tts_ms
            timings["ttfa_total_ms"] = total_ms

            timings["total"] = round(time.perf_counter() - t0, 4)

            log_pipeline_event(
                "turn_pipeline_complete",
                session_id=session_id,
                utterance_id=utterance_id,
                turn_index=turn_index,
                timings=timings,
            )
            
            latency_str = f"Total: {total_ms:.0f}ms [VAD: {vad_wait:.0f}ms | STT: {stt_ms:.0f}ms | LLM: {llm_ms:.0f}ms | TTS(1st): {tts_ms:.0f}ms]"
            log_transcript(session_id, result["transcript"], result["reply_text"], latency_str)

            return result
        except asyncio.CancelledError:
            logger.info(f"[{utterance_id}] Process task cancelled (barge-in detected).")
            if result.get("transcript"):
                log_transcript(session_id, result["transcript"], result.get("reply_text", "[Cancelled by barge-in]"), "Cancelled")
            return result

    # =====================================================================
    #  TTS helper — synthesize a single sentence
    # =====================================================================
    async def _tts_sentence(
        self,
        sentence: str,
        result: dict,
        timings: dict,
        t0: float,
        stage_cb: Callable,
        on_audio: Optional[Callable],
        cartesia_ws: Optional[Any] = None,
    ):
        """Synthesize a single sentence and deliver via callback."""
        if not sentence or not sentence.strip():
            return

        stage_cb("tts", "running", f"Synthesizing: '{sentence[:50]}…'")

        if "tts_start" not in timings:
            timings["tts_start"] = round(time.perf_counter() - t0, 4)

        cached = self.tts_cache.get(sentence)
        if cached:
            logger.info(f"TTS cache hit: '{sentence[:40]}…'")
            if "tts_first_audio" not in timings:
                timings["tts_first_audio"] = round(time.perf_counter() - t0, 4)

            if result.get("audio_bytes"):
                result["audio_bytes"] = result["audio_bytes"] + cached
            else:
                result["audio_bytes"] = cached

            if on_audio:
                try:
                    on_audio(cached)
                except Exception:
                    pass
        else:
            chunks = []
            try:
                first = True
                
                if self.tts_provider == "cartesia" and cartesia_ws:
                    voice = os.getenv("CARTESIA_VOICE_ID", "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc")
                    ws_stream = await cartesia_ws.send(
                        model_id="sonic-3",
                        transcript=sentence,
                        voice={"mode": "id", "id": voice},
                        output_format={
                            "container": "raw", 
                            "encoding": "pcm_s16le", 
                            "sample_rate": 24000
                        },
                        stream=True,
                    )
                    # We wrap the output generator so it yields bytes like the others
                    async def ws_gen():
                        async for output in ws_stream:
                            if hasattr(output, "audio") and output.audio:
                                yield output.audio
                            elif isinstance(output, dict) and "audio" in output:
                                yield output["audio"]
                    stream_gen = ws_gen()
                elif self.tts_provider == "cartesia" and self.cartesia:
                    stream_gen = self.cartesia.text_to_speech_streaming(sentence)
                else:
                    stream_gen = self.groq.text_to_speech_streaming(sentence)

                async for chunk in stream_gen:
                    if first:
                        if "tts_first_audio" not in timings:
                            timings["tts_first_audio"] = round(time.perf_counter() - t0, 4)
                        first = False
                        
                    chunks.append(chunk)

                    # Stream Cartesia PCM chunks progressively to frontend for sub-second latency
                    if on_audio and self.tts_provider == "cartesia":
                        try:
                            on_audio(chunk)
                        except Exception:
                            pass
                
                audio_chunk = b"".join(chunks)
                
                if self.tts_provider == "cartesia" and self.cartesia:
                    from app.audio_utils import build_wav
                    audio_chunk = build_wav(audio_chunk, sample_rate=24000)
                    
                self.tts_cache.put(sentence, audio_chunk)
                
                if result.get("audio_bytes"):
                    result["audio_bytes"] = result["audio_bytes"] + audio_chunk
                else:
                    result["audio_bytes"] = audio_chunk

                # Send fully combined audio file for the sentence to frontend (only if not already streamed)
                if on_audio and self.tts_provider != "cartesia":
                    try:
                        on_audio(audio_chunk)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"TTS failed for sentence: {e}")
                stage_cb("tts", "failed", str(e))
                return

        timings["tts_end"] = round(time.perf_counter() - t0, 4)
        stage_cb("tts", "done", f"Cache stats: {self.tts_cache.stats}")

    # =====================================================================
    #  LEGACY: Single-utterance streaming pipeline (unchanged API
    async def process_stream(
        self,
        audio_queue: asyncio.Queue,
        on_stt_text: Optional[Callable] = None,
        on_llm_token: Optional[Callable] = None,
        on_tts_audio: Optional[Callable] = None,
        on_stage: Optional[Callable] = None,
        call_sid: Optional[str] = None,
        update_call_with_audio: bool = True,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Entry point for Twilio phone calls (and legacy process_stream callers).
        Bridges single-utterance stream requests into the continuous conversational loop.
        """
        resolved_session_id = session_id or call_sid or str(uuid.uuid4())[:8]
        _buffer = bytearray()
        
        def wrapped_tts(audio_chunk: bytes):
            if not on_tts_audio:
                return
                
            if self.tts_provider == "cartesia":
                # Cartesia sends raw 24kHz PCM chunks without WAV headers.
                # Twilio's main.py loop expects valid WAV headers.
                _buffer.extend(audio_chunk)
                
                # Buffer size of 2400 bytes = 50ms of audio (16-bit mono 24kHz)
                while len(_buffer) >= 2400:
                    chunk = bytes(_buffer[:2400])
                    del _buffer[:2400]
                    wav_bytes = build_wav(chunk, sample_rate=24000)
                    on_tts_audio(wav_bytes)
            else:
                # Groq TTS provides complete WAV files directly.
                on_tts_audio(audio_chunk)
                
        return await self.process_continuous(
            audio_queue=audio_queue,
            on_stt_text=on_stt_text,
            on_llm_token=on_llm_token,
            on_tts_audio=wrapped_tts if on_tts_audio else None,
            on_stage=on_stage,
            session_id=resolved_session_id,
            langsmith_extra={"metadata": {"session_id": resolved_session_id, "thread_id": resolved_session_id}},
        )

    # =====================================================================
    #  Compatibility wrapper — process a complete audio buffer
    # =====================================================================
    async def process_audio_streaming(
        self,
        audio_bytes: bytes,
        call_sid: Optional[str] = None,
        is_mulaw: bool = True,
        on_stt_text: Optional[Callable] = None,
        on_llm_token: Optional[Callable] = None,
        on_tts_audio: Optional[Callable] = None,
        on_stage: Optional[Callable] = None,
        update_call_with_audio: bool = True,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Process a complete audio buffer through the streaming pipeline.

        Compatibility wrapper for callers that already have the full audio
        (e.g. /api/mic endpoint).  Feeds the audio into an asyncio.Queue
        in small chunks and runs the streaming pipeline.
        """
        if is_mulaw:
            pcm_data = mulaw_to_pcm(audio_bytes)
            pcm_16k = resample_to_16khz(pcm_data)
        else:
            pcm_16k = audio_bytes

        audio_q: asyncio.Queue = asyncio.Queue()
        chunk_size = int(16000 * 2 * 0.1)  # 100ms of 16kHz 16-bit mono

        for i in range(0, len(pcm_16k), chunk_size):
            await audio_q.put(pcm_16k[i:i + chunk_size])
        await audio_q.put(_DONE)

        return await self.process_stream(
            audio_queue=audio_q,
            on_stt_text=on_stt_text,
            on_llm_token=on_llm_token,
            on_tts_audio=on_tts_audio,
            on_stage=on_stage,
            call_sid=call_sid,
            update_call_with_audio=update_call_with_audio,
            session_id=session_id,
        )

    # =====================================================================
    #  Compatibility wrapper — process a complete audio buffer
    # =====================================================================
    async def process_audio_streaming(
        self,
        audio_bytes: bytes,
        call_sid: Optional[str] = None,
        is_mulaw: bool = True,
        on_stt_text: Optional[Callable] = None,
        on_llm_token: Optional[Callable] = None,
        on_tts_audio: Optional[Callable] = None,
        on_stage: Optional[Callable] = None,
        update_call_with_audio: bool = True,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Process a complete audio buffer through the streaming pipeline.

        Compatibility wrapper for callers that already have the full audio
        (e.g., legacy /api/call endpoint).
        """
        audio_queue: asyncio.Queue = asyncio.Queue()

        if is_mulaw:
            pcm_data = mulaw_to_pcm(audio_bytes)
            pcm_data = resample_to_16khz(pcm_data)
        else:
            pcm_data = audio_bytes

        # Feed the whole audio into the queue
        await audio_queue.put(pcm_data)
        await audio_queue.put(_DONE)

        return await self.process_stream(
            audio_queue=audio_queue,
            call_sid=call_sid,
            on_stt_text=on_stt_text,
            on_llm_token=on_llm_token,
            on_tts_audio=on_tts_audio,
            on_stage=on_stage,
            update_call_with_audio=update_call_with_audio,
            session_id=session_id,
        )
# =============================================================================
# Utility functions
# =============================================================================


def _split_sentences(text: str) -> list[str]:
    """
    Split text on sentence boundaries (.!?) for incremental TTS.

    Returns a list where the last element may be an incomplete sentence.
    """
    parts = re.split(r'(?<=[.!?])\s+', text)
    return parts if parts else [text]


def _serialize_customer(customer: Optional[dict]) -> Optional[dict]:
    """Ensure customer dict is JSON-serializable."""
    if not customer:
        return None
    result = dict(customer)
    if "date_of_birth" in result and hasattr(result["date_of_birth"], "isoformat"):
        result["date_of_birth"] = result["date_of_birth"].isoformat()
    return result
