"""
Streaming voice pipeline — concurrent STT → LLM → TTS with asyncio queues.

Replaces the sequential batch pipeline with three overlapping async workers:
  1. STT worker  — consumes audio chunks, fires early + final transcriptions
  2. LLM worker  — consumes transcript text, streams tokens, buffers sentences
  3. TTS worker  — consumes sentences, checks cache, synthesizes audio

Each worker reads from an input queue and writes to the next worker's queue,
so processing overlaps maximally.
"""

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from app.audio_utils import (
    build_wav,
    mulaw_to_pcm,
    resample_to_16khz,
    detect_silence,
    trim_trailing_silence,
)
from app.config import settings
from app.database import DatabaseClient
from app.groq_client import GroqClient
from app.response_cache import ResponseCache
from app.twilio_handler import TwilioHandler

logger = logging.getLogger(__name__)

# Audio cache directory
AUDIO_CACHE_DIR = Path("audio_cache")
AUDIO_CACHE_DIR.mkdir(exist_ok=True)

# Sentinel to signal a queue that no more items are coming
_DONE = object()


class StreamingVoicePipeline:
    """
    Concurrent streaming pipeline:  Audio → STT → LLM → TTS → Audio output.

    Three async workers connected by asyncio.Queues.  Each worker starts
    producing output for the next stage as soon as data is available,
    overlapping computation for sub-1s latency.
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
    ):
        self.groq = groq_client
        self.db = db_client
        self.twilio = twilio_handler
        self.tts_cache = ResponseCache(max_size=settings.TTS_CACHE_SIZE)

    # =====================================================================
    #  Main entry point — full streaming pipeline
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
    ) -> dict:
        """
        Run the full streaming pipeline.

        Args:
            audio_queue: Queue of raw PCM audio chunks (bytes).
                         Producer should put _DONE when the user stops speaking.
            on_stt_text: Callback(text: str) — called with partial/final transcript.
            on_llm_token: Callback(token: str) — called for each LLM token.
            on_tts_audio: Callback(audio_bytes: bytes) — called for each TTS chunk.
            on_stage: Callback(stage: str, status: str, detail: str) — stage updates.
            call_sid: Twilio Call SID, if from a real call.
            update_call_with_audio: Whether to update the call with a Play URL at the end.

        Returns:
            Result dict with transcript, intent, reply_text, audio data, timings.
        """
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        # Queues connecting the three workers
        stt_to_llm: asyncio.Queue = asyncio.Queue()
        llm_to_tts: asyncio.Queue = asyncio.Queue()
        tts_output: asyncio.Queue = asyncio.Queue()

        # Shared result dict that workers populate
        result: dict[str, Any] = {
            "transcript": "",
            "intent": "unknown",
            "customer": None,
            "orders": [],
            "reply_text": "",
            "audio_bytes": b"",
            "audio_url": "",
            "audio_path": "",
            "stages": [],
            "timings": timings,
        }

        def _stage(name: str, status: str, detail: str = ""):
            result["stages"].append({
                "stage": name, "status": status,
                "detail": detail, "ts": datetime.now().isoformat(),
            })
            if on_stage:
                try:
                    on_stage(name, status, detail)
                except Exception:
                    pass

        # Launch the three workers concurrently
        stt_task = asyncio.create_task(
            self._stt_worker(audio_queue, stt_to_llm, result, timings, _stage, on_stt_text)
        )
        llm_task = asyncio.create_task(
            self._llm_worker(stt_to_llm, llm_to_tts, result, timings, _stage, on_llm_token)
        )
        tts_task = asyncio.create_task(
            self._tts_worker(llm_to_tts, tts_output, result, timings, _stage, on_tts_audio)
        )

        # Wait for all three workers to complete
        await asyncio.gather(stt_task, llm_task, tts_task)

        # Collect all TTS audio from the output queue
        audio_parts = []
        while not tts_output.empty():
            item = tts_output.get_nowait()
            if item is not _DONE and isinstance(item, bytes):
                audio_parts.append(item)

        if audio_parts:
            combined_audio = b"".join(audio_parts)
            result["audio_bytes"] = combined_audio

            # Save to file
            file_id = call_sid or str(uuid.uuid4())[:8]
            filename = f"{file_id}_{int(datetime.now().timestamp())}.wav"
            filepath = AUDIO_CACHE_DIR / filename
            filepath.write_bytes(combined_audio)

            audio_url = f"{settings.SERVER_HOST}/audio/{filename}"
            result["audio_url"] = audio_url
            result["audio_path"] = str(filepath)
            logger.info(f"Combined audio saved: {filepath} ({len(combined_audio)} bytes)")

            # If Twilio call, redirect to play audio
            if call_sid and update_call_with_audio:
                await self.twilio.update_call_with_audio(call_sid, audio_url)

        timings["total"] = round(time.perf_counter() - t0, 4)
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
    ) -> dict:
        """
        Process a complete audio buffer through the streaming pipeline.

        Compatibility wrapper for callers that already have the full audio
        (e.g. /api/mic endpoint).  Feeds the audio into an asyncio.Queue
        in small chunks and runs the streaming pipeline.
        """
        # Prepare audio
        if is_mulaw:
            pcm_data = mulaw_to_pcm(audio_bytes)
            pcm_16k = resample_to_16khz(pcm_data)
        else:
            # Assume raw PCM or browser blob — pass through
            pcm_16k = audio_bytes

        # Feed into an audio queue in chunks
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
        )

    # =====================================================================
    #  Worker 1: STT — consume audio chunks, produce transcript
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

        # How many bytes = early chunk threshold
        early_bytes = int(16000 * 2 * settings.STT_EARLY_CHUNK_SECONDS)
        silence_chunks_for_eos = int(settings.SILENCE_DURATION_MS / 20)  # 20ms per chunk

        try:
            while True:
                item = await audio_queue.get()
                if item is _DONE:
                    break

                chunk = bytes(item)
                audio_buffer.extend(chunk)

                # VAD: detect speech vs silence
                if detect_silence(chunk, settings.SILENCE_THRESHOLD):
                    silence_counter += 1
                else:
                    silence_counter = 0
                    has_speech = True

                # Early STT: fire on first ~1.5s of speech
                if has_speech and not early_stt_fired and len(audio_buffer) >= early_bytes:
                    early_stt_fired = True
                    timings["stt_early_start"] = round(time.perf_counter() - t_start, 4)

                    # Trim and transcribe the early chunk
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
                input_filename = f"input_{str(uuid.uuid4())[:8]}_{int(datetime.now().timestamp())}.wav"
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

                    # Use whichever transcript is longer/better
                    transcript = final_transcript if len(final_transcript) >= len(early_transcript) else early_transcript
                    result["transcript"] = transcript
                    stage_cb("stt", "done", transcript)
                    logger.info(f"Final STT: '{transcript}'")

                    if on_text:
                        try:
                            on_text(transcript)
                        except Exception:
                            pass

                    # Push transcript to LLM worker
                    await output_queue.put(transcript)

                except Exception as e:
                    logger.error(f"Final STT failed: {e}")
                    # Fall back to early transcript
                    if early_transcript:
                        result["transcript"] = early_transcript
                        await output_queue.put(early_transcript)
                    stage_cb("stt", "failed", str(e))
            elif early_transcript:
                # Only have early transcript
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
    #  Worker 2: LLM — consume transcript, produce sentence chunks
    # =====================================================================
    async def _llm_worker(
        self,
        input_queue: asyncio.Queue,
        output_queue: asyncio.Queue,
        result: dict,
        timings: dict,
        stage_cb: Callable,
        on_token: Optional[Callable],
    ):
        """
        Consume transcript text from *input_queue*.
        Run intent detection + DB lookup, then stream LLM tokens.
        Buffer tokens into sentences and push each sentence to *output_queue*.
        """
        t_start = time.perf_counter()

        try:
            # Wait for transcript from STT
            transcript = await input_queue.get()
            if transcript is _DONE or not transcript:
                stage_cb("llm", "done", "No transcript to process")
                return

            # --- Intent detection + DB lookup ---
            stage_cb("intent", "running")
            intent, extracted = self._detect_intent(transcript)
            result["intent"] = intent
            stage_cb("intent", "done", f"intent={intent}")

            if intent == "order_status" and extracted.get("name"):
                stage_cb("db_lookup", "running")
                dob = extracted.get("dob", "")
                customer = await self.db.verify_customer(extracted["name"], dob)
                result["customer"] = _serialize_customer(customer)

                if customer:
                    orders = await self.db.get_all_orders(customer["id"])
                    result["orders"] = orders
                    stage_cb("db_lookup", "done", f"customer={customer['full_name']}, orders={len(orders)}")
                else:
                    stage_cb("db_lookup", "done", "Customer not found")

            # --- Build LLM messages ---
            stage_cb("llm", "running", "Generating response…")
            messages = self._build_llm_messages(result, transcript)

            # --- Stream LLM tokens, buffer into sentences ---
            timings["llm_start"] = round(time.perf_counter() - t_start, 4)
            first_token_received = False
            token_buffer = []
            full_reply_parts = []

            async for token in self.groq.chat_completion_stream_tokens(
                messages,
                max_tokens=settings.LLM_MAX_TOKENS,
            ):
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

                # Check if we have a complete sentence
                current_text = "".join(token_buffer)
                sentences = _split_sentences(current_text)

                if len(sentences) > 1:
                    # Push all complete sentences, keep the partial last one
                    for sentence in sentences[:-1]:
                        sentence = sentence.strip()
                        if sentence:
                            await output_queue.put(sentence)
                    token_buffer = [sentences[-1]]

            # Push any remaining text
            remaining = "".join(token_buffer).strip()
            if remaining:
                await output_queue.put(remaining)

            full_reply = "".join(full_reply_parts).strip()
            result["reply_text"] = full_reply
            timings["llm_end"] = round(time.perf_counter() - t_start, 4)
            stage_cb("llm", "done", full_reply[:80])

        except Exception as e:
            logger.exception(f"LLM worker error: {e}")
            stage_cb("llm", "failed", str(e))
            # Push a fallback reply
            fallback = self._fallback_reply(result)
            result["reply_text"] = fallback
            await output_queue.put(fallback)
        finally:
            await output_queue.put(_DONE)

    # =====================================================================
    #  Worker 3: TTS — consume sentences, produce audio
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

                # Check cache first
                cached = self.tts_cache.get(sentence)
                if cached:
                    logger.info(f"TTS cache hit: '{sentence[:40]}…'")
                    audio_chunk = cached
                else:
                    # Call TTS API
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

    # =====================================================================
    #  Internal helpers
    # =====================================================================
    def _detect_intent(self, text: str) -> tuple[str, dict]:
        """Simple keyword-based intent detection and entity extraction."""
        text_lower = text.lower()
        extracted = {}

        order_keywords = ["order", "status", "shipping", "delivery", "track", "package", "shipped"]
        is_order_query = any(kw in text_lower for kw in order_keywords)

        # Extract name — allow single or multiple words with simple cleanup
        name = self._extract_name(text)
        if name:
            extracted["name"] = name

        # Extract DOB
        month_name = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        dob_patterns = [
            r"born\s+(?:on\s+)?(\w+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
            rf"born\s+(?:on\s+)?(\d{{1,2}}(?:st|nd|rd|th)?\s+{month_name}\s+\d{{4}})",
            r"(?:date of birth|dob|d\.o\.b\.?)\s+(?:is\s+)?(\d{4}-\d{2}-\d{2})",
            r"(?:date of birth|dob|d\.o\.b\.?)\s+(?:is\s+)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
            r"born\s+(?:on\s+)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        ]
        for pattern in dob_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted["dob"] = _parse_date_string(match.group(1))
                break

        if "dob" not in extracted:
            fallback_patterns = [
                rf"\b(\d{{1,2}}(?:st|nd|rd|th)?\s+{month_name}\s+\d{{4}})\b",
                rf"\b({month_name}\s+\d{{1,2}}(?:st|nd|rd|th)?[,]?\s+\d{{4}})\b",
                r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\b",
                r"\b(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b",
            ]
            for pattern in fallback_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    extracted["dob"] = _parse_date_string(match.group(1))
                    break

        intent = "order_status" if is_order_query else "general"
        return intent, extracted

    def _extract_name(self, text: str) -> Optional[str]:
        """Extract a name from common phrases and normalize it."""
        name_patterns = [
            r"(?:my name is|i am|i'm|this is|call me)\s+([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,5})",
            r"(?:name is|name's)\s+([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,5})",
        ]
        stopwords = {"and", "my", "dob", "date", "birth", "is", "was", "am", "i", "im", "born", "on"}

        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            raw = re.sub(r"[^A-Za-z'\-\s]", "", match.group(1))
            parts = [p for p in raw.split() if p]
            while parts and parts[-1].lower() in stopwords:
                parts.pop()

            cleaned = " ".join(parts).strip()
            if cleaned:
                return cleaned

        return None

    def _build_llm_messages(self, result: dict, user_text: str) -> list[dict]:
        """Build the LLM message list with context from DB results."""
        customer = result.get("customer")
        orders = result.get("orders", [])

        context_parts = []
        if customer:
            context_parts.append(f"Customer verified: {customer.get('full_name', 'Unknown')}.")
        else:
            context_parts.append("Customer not found in database.")

        if orders:
            orders_str = "; ".join(
                f"#{o['order_number']} {o['status']} ETA:{o.get('estimated_arrival', 'N/A')}"
                for o in orders
            )
            context_parts.append(f"Orders: {orders_str}")
        elif customer:
            context_parts.append("No orders found.")

        context = " ".join(context_parts)

        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "system", "content": f"Context: {context}"},
            {"role": "user", "content": user_text},
        ]

    def _fallback_reply(self, result: dict) -> str:
        """Generate a fallback reply when the LLM fails."""
        orders = result.get("orders", [])
        customer = result.get("customer")

        if orders:
            o = orders[0]
            return (
                f"You have {len(orders)} orders. Your latest order {o['order_number']} "
                f"is {o['status']}. ETA: {o.get('estimated_arrival', 'not available')}."
            )
        elif customer:
            return "I found your account, but there are no recent orders on file."
        else:
            return "I wasn't able to find an account matching that information."


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


def _now() -> str:
    return datetime.now().isoformat()


def _parse_date_string(date_str: str) -> str:
    """Parse various date formats into YYYY-MM-DD."""
    date_str = date_str.strip().rstrip(",")
    date_str = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", date_str, flags=re.IGNORECASE)

    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    for fmt in ("%d %B %Y", "%d %B, %Y", "%d %b %Y", "%d %b, %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    match = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", date_str)
    if match:
        month, day, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    match = re.match(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", date_str)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    return date_str


def _serialize_customer(customer: Optional[dict]) -> Optional[dict]:
    """Ensure customer dict is JSON-serializable."""
    if not customer:
        return None
    result = dict(customer)
    if "date_of_birth" in result and hasattr(result["date_of_birth"], "isoformat"):
        result["date_of_birth"] = result["date_of_birth"].isoformat()
    return result
