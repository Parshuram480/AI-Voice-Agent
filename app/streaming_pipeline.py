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
import logging
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
)
from app.config import settings
from app.database import DatabaseClient
from app.groq_client import GroqClient
from app.llm.rephrase import LLMRephraser
from app.services.conversation_service import ConversationService
from app.logging.logger import log_event, log_pipeline_event
from app.response_cache import ResponseCache
from app.twilio_handler import TwilioHandler

logger = logging.getLogger(__name__)

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
        conversation_service: ConversationService,
        rephraser: LLMRephraser,
    ):
        self.groq = groq_client
        self.db = db_client
        self.twilio = twilio_handler
        self.tts_cache = ResponseCache(max_size=settings.TTS_CACHE_SIZE)
        self.conversation = conversation_service
        self.rephraser = rephraser

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

        def _set_phase(phase: ConversationPhase):
            if on_phase_change:
                try:
                    on_phase_change(phase.value)
                except Exception:
                    pass

        _set_phase(ConversationPhase.LISTENING)
        log_pipeline_event("session_start", session_id=resolved_session_id)

        while not session_ended:
            turn_index += 1
            utterance_id = f"{resolved_session_id}-t{turn_index}"

            log_pipeline_event(
                "turn_start",
                session_id=resolved_session_id,
                utterance_id=utterance_id,
                turn_index=turn_index,
            )

            # ----- Step 1: VAD — collect one utterance from the audio stream -----
            _set_phase(ConversationPhase.LISTENING)
            utterance_audio, vad_done_reason = await self._vad_collect_utterance(
                audio_queue,
                session_id=resolved_session_id,
                utterance_id=utterance_id,
                on_phase_change=_set_phase,
                on_stage=on_stage,
            )

            if vad_done_reason == "stream_ended":
                log_pipeline_event(
                    "stream_ended",
                    session_id=resolved_session_id,
                    utterance_id=utterance_id,
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
                    utterance_id=utterance_id,
                    turn_index=turn_index,
                    bytes=len(utterance_audio) if utterance_audio else 0,
                )
                if session_ended:
                    break
                continue

            # ----- Step 2: Process the utterance (STT → LLM → TTS) -----
            _set_phase(ConversationPhase.PROCESSING)
            log_pipeline_event(
                "utterance_finalized",
                session_id=resolved_session_id,
                utterance_id=utterance_id,
                turn_index=turn_index,
                audio_bytes=len(utterance_audio),
            )

            turn_result = await self._process_single_utterance(
                utterance_audio,
                session_id=resolved_session_id,
                utterance_id=utterance_id,
                turn_index=turn_index,
                on_stt_text=on_stt_text,
                on_llm_token=on_llm_token,
                on_tts_audio=on_tts_audio,
                on_stage=on_stage,
                on_phase_change=_set_phase,
            )

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
                break

            # ----- Step 3: Resume listening -----
            _set_phase(ConversationPhase.LISTENING)
            log_pipeline_event(
                "turn_complete",
                session_id=resolved_session_id,
                utterance_id=utterance_id,
                turn_index=turn_index,
                timings=turn_result.get("timings", {}),
            )

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
    ) -> tuple[Optional[bytes], str]:
        """
        Listen to the audio_queue and collect frames for one utterance.

        Uses energy-based VAD:
        1. Wait for speech to start (frames above silence threshold)
        2. Once speech starts, buffer all frames
        3. When silence exceeds VAD_SILENCE_MS, finalize the utterance

        Returns:
            (utterance_pcm_bytes, reason)
            reason is one of: "silence", "max_duration", "stream_ended"
        """
        audio_buffer = bytearray()
        speech_started = False
        silence_ms = 0.0
        speech_ms = 0.0
        t_start = time.perf_counter()
        last_vad_log = t_start

        # Configuration
        silence_threshold = settings.SILENCE_THRESHOLD
        vad_silence_ms = max(1, settings.VAD_SILENCE_MS)
        min_speech_ms = max(1, settings.MIN_SPEECH_MS)
        sample_rate = 16000
        sample_width = 2
        # Max utterance in bytes (16kHz, 16-bit mono = 32000 bytes/sec)
        max_utterance_bytes = int(settings.MAX_UTTERANCE_MS / 1000 * 16000 * 2)

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
                        return bytes(audio_buffer), "silence"
                continue

            if item is _DONE:
                # Stream ended
                if speech_started and audio_buffer:
                    return bytes(audio_buffer), "stream_ended"
                return None, "stream_ended"

            chunk = bytes(item)

            chunk_ms = (len(chunk) / (sample_width * sample_rate)) * 1000.0 if chunk else 0.0
            rms = compute_rms(chunk, sample_width=sample_width) if chunk else 0

            is_silence = detect_silence(chunk, silence_threshold)

            if not speech_started:
                if not is_silence:
                    speech_started = True
                    speech_ms = chunk_ms
                    silence_ms = 0.0
                    audio_buffer.extend(chunk)
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
                audio_buffer.extend(chunk)

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
                if silence_ms >= vad_silence_ms and speech_ms >= min_speech_ms:
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
                    return bytes(audio_buffer), "silence"

                # Check max utterance duration
                if len(audio_buffer) >= max_utterance_bytes:
                    log_pipeline_event(
                        "max_utterance_reached",
                        session_id=session_id,
                        utterance_id=utterance_id,
                        duration_ms=settings.MAX_UTTERANCE_MS,
                    )
                    if on_stage:
                        try:
                            on_stage("vad", "done", "Max utterance duration reached")
                        except Exception:
                            pass
                    return bytes(audio_buffer), "max_duration"

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
        on_stt_text: Optional[Callable] = None,
        on_llm_token: Optional[Callable] = None,
        on_tts_audio: Optional[Callable] = None,
        on_stage: Optional[Callable] = None,
        on_phase_change: Optional[Callable] = None,
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

        # ------ STT ------
        _stage("stt", "running", "Transcribing utterance…")
        timings["stt_start"] = round(time.perf_counter() - t0, 4)

        trimmed_pcm = trim_trailing_silence(utterance_pcm)
        wav_bytes = build_wav(trimmed_pcm, sample_rate=16000)

        # Save input audio
        input_filename = f"input_{utterance_id}_{int(datetime.now(UTC).timestamp())}.wav"
        input_filepath = AUDIO_CACHE_DIR / input_filename
        input_filepath.write_bytes(wav_bytes)
        result["input_audio_url"] = f"{settings.SERVER_HOST}/audio/{input_filename}"

        try:
            transcript = await self.groq.speech_to_text(wav_bytes, ext="wav")
            timings["stt_end"] = round(time.perf_counter() - t0, 4)
            timings["stt_duration"] = round(timings["stt_end"] - timings["stt_start"], 4)
            result["transcript"] = transcript
            _stage("stt", "done", transcript)
            logger.info(f"[{utterance_id}] STT: '{transcript}'")

            log_pipeline_event(
                "stt_complete",
                session_id=session_id,
                utterance_id=utterance_id,
                turn_index=turn_index,
                duration_ms=timings["stt_duration"] * 1000,
                transcript=transcript[:100],
            )

            if on_stt_text:
                try:
                    on_stt_text(transcript)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[{utterance_id}] STT failed: {e}")
            _stage("stt", "failed", str(e))
            timings["stt_end"] = round(time.perf_counter() - t0, 4)
            result["reply_text"] = "I'm sorry, I couldn't understand that. Could you repeat?"
            return result

        if not transcript or not transcript.strip():
            _stage("stt", "done", "No speech detected")
            result["reply_text"] = ""
            return result

        # ------ Conversation Service (intent + verification + DB) ------
        _stage("conversation", "running", "Routing intent and slots")
        timings["conversation_start"] = round(time.perf_counter() - t0, 4)

        try:
            conversation = await self.conversation.handle_user_text(session_id, transcript)
            result["intent"] = conversation.intent
            result["reply_text"] = conversation.reply_text
            result["state"] = conversation.state
            result["verified"] = conversation.verified
            result["customer"] = _serialize_customer(conversation.customer)
            result["orders"] = conversation.orders
            result["should_end"] = conversation.should_end
            timings.update(conversation.timings)
            timings["conversation_end"] = round(time.perf_counter() - t0, 4)
            timings["conversation_duration"] = round(
                timings["conversation_end"] - timings["conversation_start"], 4
            )
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
            logger.error(f"[{utterance_id}] Conversation service error: {e}")
            _stage("conversation", "failed", str(e))
            result["reply_text"] = "I'm sorry, something went wrong. Please try again."
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
                                    sentence, result, timings, t0, _stage, on_tts_audio
                                )
                        token_buffer = [sentences[-1]]

                remaining = "".join(token_buffer).strip()
                if remaining:
                    await self._tts_sentence(
                        remaining, result, timings, t0, _stage, on_tts_audio
                    )

                full_reply = "".join(full_reply_parts).strip()
                result["reply_text"] = full_reply or reply_text
                timings["llm_end"] = round(time.perf_counter() - t0, 4)
                _stage("llm", "done", result["reply_text"][:80])

            except Exception as e:
                logger.error(f"[{utterance_id}] LLM rephrase failed: {e}")
                _stage("llm", "failed", "Rephrase failed — using original")
                await self._tts_sentence(
                    reply_text, result, timings, t0, _stage, on_tts_audio
                )
        else:
            _stage("llm", "done", "Deterministic response")
            # TTS the reply directly
            await self._tts_sentence(
                reply_text, result, timings, t0, _stage, on_tts_audio
            )

        if on_phase_change:
            on_phase_change(ConversationPhase.SPEAKING.value)

        timings["total"] = round(time.perf_counter() - t0, 4)

        log_pipeline_event(
            "turn_pipeline_complete",
            session_id=session_id,
            utterance_id=utterance_id,
            turn_index=turn_index,
            timings=timings,
        )

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
            audio_chunk = cached
        else:
            try:
                audio_chunk = await self.groq.text_to_speech(sentence)
                self.tts_cache.put(sentence, audio_chunk)
            except Exception as e:
                logger.error(f"TTS failed for sentence: {e}")
                stage_cb("tts", "failed", str(e))
                return

        if "tts_first_audio" not in timings:
            timings["tts_first_audio"] = round(time.perf_counter() - t0, 4)

        # Accumulate audio in result
        if result.get("audio_bytes"):
            result["audio_bytes"] = result["audio_bytes"] + audio_chunk
        else:
            result["audio_bytes"] = audio_chunk

        if on_audio:
            try:
                on_audio(audio_chunk)
            except Exception:
                pass

        timings["tts_end"] = round(time.perf_counter() - t0, 4)
        stage_cb("tts", "done", f"Cache stats: {self.tts_cache.stats}")

    # =====================================================================
    #  LEGACY: Single-utterance streaming pipeline (unchanged API)
    # =====================================================================
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
        Run the full streaming pipeline (single utterance — legacy mode).

        Kept for backward compatibility with Twilio and /api/mic endpoints.
        """
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        stt_to_llm: asyncio.Queue = asyncio.Queue()
        llm_to_tts: asyncio.Queue = asyncio.Queue()
        tts_output: asyncio.Queue = asyncio.Queue()

        resolved_session_id = session_id or call_sid or str(uuid.uuid4())[:8]

        result: dict[str, Any] = {
            "session_id": resolved_session_id,
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

        stt_task = asyncio.create_task(
            self._stt_worker(audio_queue, stt_to_llm, result, timings, _stage, on_stt_text)
        )
        llm_task = asyncio.create_task(
            self._llm_worker(
                stt_to_llm, llm_to_tts, result, timings, _stage, on_llm_token,
                resolved_session_id,
            )
        )
        tts_task = asyncio.create_task(
            self._tts_worker(llm_to_tts, tts_output, result, timings, _stage, on_tts_audio)
        )

        await asyncio.gather(stt_task, llm_task, tts_task)

        audio_parts = []
        while not tts_output.empty():
            item = tts_output.get_nowait()
            if item is not _DONE and isinstance(item, bytes):
                audio_parts.append(item)

        if audio_parts:
            combined_audio = b"".join(audio_parts)
            result["audio_bytes"] = combined_audio

            file_id = call_sid or str(uuid.uuid4())[:8]
            filename = f"output_{file_id}_{int(datetime.now(UTC).timestamp())}.wav"
            filepath = AUDIO_CACHE_DIR / filename
            filepath.write_bytes(combined_audio)

            audio_url = f"{settings.SERVER_HOST}/audio/{filename}"
            result["audio_url"] = audio_url
            result["audio_path"] = str(filepath)
            logger.info(f"Combined audio saved: {filepath} ({len(combined_audio)} bytes)")

            if call_sid and update_call_with_audio:
                await self.twilio.update_call_with_audio(call_sid, audio_url)

        timings["total"] = round(time.perf_counter() - t0, 4)
        log_event(
            "streaming_pipeline_complete",
            session_id=resolved_session_id,
            intent=result.get("intent"),
            state=result.get("state"),
            verified=result.get("verified"),
            timings=timings,
        )
        logger.info(f"Pipeline complete — timings: {timings}")
        return result

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
    #  Worker 1: STT — consume audio chunks, produce transcript (LEGACY)
    # =====================================================================
    async def _stt_worker(
        self,
        audio_queue: asyncio.Queue,
        output_queue: asyncio.Queue,
        result: dict,
        timings: dict,
        stage_cb: Callable,
        on_text: Optional[Callable],
    ):
        """
        Consume PCM audio chunks from *audio_queue*.
        Fires "early STT" on the first ~1.5s of speech for a head-start,
        then a final STT on the complete utterance.
        Pushes the final transcript text to *output_queue*.
        """
        stage_cb("stt", "running", "Waiting for audio…")
        audio_buffer = bytearray()
        early_stt_fired = False
        early_transcript = ""
        has_speech = False
        silence_counter = 0
        t_start = time.perf_counter()

        early_bytes = int(16000 * 2 * settings.STT_EARLY_CHUNK_SECONDS)
        silence_chunks_for_eos = int(settings.SILENCE_DURATION_MS / 20)

        try:
            while True:
                item = await audio_queue.get()
                if item is _DONE:
                    break

                chunk = bytes(item)
                audio_buffer.extend(chunk)

                if detect_silence(chunk, settings.SILENCE_THRESHOLD):
                    silence_counter += 1
                else:
                    silence_counter = 0
                    has_speech = True

                if has_speech and not early_stt_fired and len(audio_buffer) >= early_bytes:
                    early_stt_fired = True
                    timings["stt_early_start"] = round(time.perf_counter() - t_start, 4)

                    early_pcm = bytes(audio_buffer[:early_bytes])
                    early_pcm = trim_trailing_silence(early_pcm)
                    wav_bytes = build_wav(early_pcm, sample_rate=16000)

                    try:
                        early_transcript = await self.groq.speech_to_text(wav_bytes, ext="wav")
                        timings["stt_early_end"] = round(time.perf_counter() - t_start, 4)
                        logger.info(f"Early STT: '{early_transcript}'")

                        if early_transcript and on_text:
                            try:
                                on_text(early_transcript)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(f"Early STT failed: {e}")

                if has_speech and silence_counter >= silence_chunks_for_eos:
                    logger.info("VAD: end-of-speech detected during streaming")
                    break

            # Save input audio
            if audio_buffer:
                input_filename = f"input_{str(uuid.uuid4())[:8]}_{int(datetime.now(UTC).timestamp())}.wav"
                input_filepath = AUDIO_CACHE_DIR / input_filename
                wav_bytes_full = build_wav(bytes(audio_buffer), sample_rate=16000)
                input_filepath.write_bytes(wav_bytes_full)
                input_audio_url = f"{settings.SERVER_HOST}/audio/{input_filename}"
                result["input_audio_url"] = input_audio_url

            # Final STT on the complete audio
            if has_speech and len(audio_buffer) > 3200:
                timings["stt_final_start"] = round(time.perf_counter() - t_start, 4)
                stage_cb("stt", "running", "Final transcription…")

                final_pcm = trim_trailing_silence(bytes(audio_buffer))
                wav_bytes = build_wav(final_pcm, sample_rate=16000)

                try:
                    final_transcript = await self.groq.speech_to_text(wav_bytes, ext="wav")
                    timings["stt_final_end"] = round(time.perf_counter() - t_start, 4)

                    transcript = final_transcript if len(final_transcript) >= len(early_transcript) else early_transcript
                    result["transcript"] = transcript
                    stage_cb("stt", "done", transcript)
                    logger.info(f"Final STT: '{transcript}'")

                    if on_text:
                        try:
                            on_text(transcript)
                        except Exception:
                            pass

                    await output_queue.put(transcript)

                except Exception as e:
                    logger.error(f"Final STT failed: {e}")
                    if early_transcript:
                        result["transcript"] = early_transcript
                        await output_queue.put(early_transcript)
                    stage_cb("stt", "failed", str(e))
            elif early_transcript:
                result["transcript"] = early_transcript
                await output_queue.put(early_transcript)
                stage_cb("stt", "done", early_transcript)
            else:
                stage_cb("stt", "done", "No speech detected")

        except Exception as e:
            logger.exception(f"STT worker error: {e}")
            stage_cb("stt", "failed", str(e))
        finally:
            await output_queue.put(_DONE)

    # =====================================================================
    #  Worker 2: LLM — consume transcript, produce sentence chunks (LEGACY)
    # =====================================================================
    async def _llm_worker(
        self,
        input_queue: asyncio.Queue,
        output_queue: asyncio.Queue,
        result: dict,
        timings: dict,
        stage_cb: Callable,
        on_token: Optional[Callable],
        session_id: str,
    ):
        """
        Consume transcript text from *input_queue*.
        Run intent detection + DB lookup, then stream LLM tokens.
        Buffer tokens into sentences and push each sentence to *output_queue*.
        """
        t_start = time.perf_counter()

        try:
            transcript = await input_queue.get()
            if transcript is _DONE or not transcript:
                stage_cb("llm", "done", "No transcript to process")
                return

            stage_cb("conversation", "running", "Routing intent and slots")
            conversation = await self.conversation.handle_user_text(session_id, transcript)
            result["intent"] = conversation.intent
            result["reply_text"] = conversation.reply_text
            result["state"] = conversation.state
            result["verified"] = conversation.verified
            result["customer"] = _serialize_customer(conversation.customer)
            result["orders"] = conversation.orders
            timings.update(conversation.timings)
            stage_cb("conversation", "done", f"intent={conversation.intent}, state={conversation.state}")

            reply_text = conversation.reply_text
            if not reply_text:
                reply_text = "I'm sorry, I couldn't process that. Please try again."
                result["reply_text"] = reply_text

            if self.rephraser and self.rephraser.enabled:
                stage_cb("llm", "running", "Rephrasing response…")
                timings["llm_start"] = round(time.perf_counter() - t_start, 4)
                first_token_received = False
                token_buffer = []
                full_reply_parts = []

                try:
                    async for token in self.rephraser.stream_rephrase(reply_text):
                        if not first_token_received:
                            timings["llm_first_token"] = round(time.perf_counter() - t_start, 4)
                            first_token_received = True

                        token_buffer.append(token)
                        full_reply_parts.append(token)

                        if on_token:
                            try:
                                on_token(token)
                            except Exception:
                                pass

                        current_text = "".join(token_buffer)
                        sentences = _split_sentences(current_text)

                        if len(sentences) > 1:
                            for sentence in sentences[:-1]:
                                sentence = sentence.strip()
                                if sentence:
                                    await output_queue.put(sentence)
                            token_buffer = [sentences[-1]]

                    remaining = "".join(token_buffer).strip()
                    if remaining:
                        await output_queue.put(remaining)

                    full_reply = "".join(full_reply_parts).strip()
                    result["reply_text"] = full_reply or reply_text
                    timings["llm_end"] = round(time.perf_counter() - t_start, 4)
                    stage_cb("llm", "done", result["reply_text"][:80])
                except Exception as e:
                    logger.error(f"LLM rephrase failed: {e}")
                    await output_queue.put(reply_text)
                    stage_cb("llm", "failed", "Rephrase failed")
            else:
                stage_cb("llm", "done", "Deterministic response")
                await output_queue.put(reply_text)
                result["reply_text"] = reply_text

        except Exception as e:
            logger.exception(f"LLM worker error: {e}")
            stage_cb("llm", "failed", str(e))
            fallback = "I'm sorry, I'm not able to help with that yet. Please ask about your orders or delivery status."
            result["reply_text"] = fallback
            await output_queue.put(fallback)
        finally:
            await output_queue.put(_DONE)

    # =====================================================================
    #  Worker 3: TTS — consume sentences, produce audio (LEGACY)
    # =====================================================================
    async def _tts_worker(
        self,
        input_queue: asyncio.Queue,
        output_queue: asyncio.Queue,
        result: dict,
        timings: dict,
        stage_cb: Callable,
        on_audio: Optional[Callable],
    ):
        """
        Consume sentence strings from *input_queue*.
        Check cache first, then call TTS for each sentence.
        Push audio bytes to *output_queue*.
        """
        t_start = time.perf_counter()
        first_audio_sent = False

        try:
            while True:
                sentence = await input_queue.get()
                if sentence is _DONE:
                    break

                if not sentence or not sentence.strip():
                    continue

                stage_cb("tts", "running", f"Synthesizing: '{sentence[:50]}…'")

                cached = self.tts_cache.get(sentence)
                if cached:
                    logger.info(f"TTS cache hit: '{sentence[:40]}…'")
                    audio_chunk = cached
                else:
                    try:
                        audio_chunk = await self.groq.text_to_speech(sentence)
                        self.tts_cache.put(sentence, audio_chunk)
                    except Exception as e:
                        logger.error(f"TTS failed for sentence: {e}")
                        continue

                if not first_audio_sent:
                    timings["tts_first_audio"] = round(time.perf_counter() - t_start, 4)
                    first_audio_sent = True

                await output_queue.put(audio_chunk)

                if on_audio:
                    try:
                        on_audio(audio_chunk)
                    except Exception:
                        pass

            timings["tts_end"] = round(time.perf_counter() - t_start, 4)
            stage_cb("tts", "done", f"Cache stats: {self.tts_cache.stats}")

        except Exception as e:
            logger.exception(f"TTS worker error: {e}")
            stage_cb("tts", "failed", str(e))
        finally:
            await output_queue.put(_DONE)

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
