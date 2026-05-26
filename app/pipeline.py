"""
Voice pipeline orchestrator — ties STT, LLM, database, and TTS together.

This is the central processing engine: given raw audio or text input,
it runs the full pipeline and produces an audio response.
"""

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings
from app.groq_client import GroqClient
from app.database import DatabaseClient
from app.twilio_handler import TwilioHandler
from app.audio_utils import build_wav, resample_to_16khz, mulaw_to_pcm

logger = logging.getLogger(__name__)

# Directory to cache generated TTS audio files
AUDIO_CACHE_DIR = Path("audio_cache")
AUDIO_CACHE_DIR.mkdir(exist_ok=True)


class VoicePipeline:
    """
    Orchestrates the full voice agent pipeline:
        Audio → STT → Intent/DB/LLM → TTS → Audio response

    Each stage is async for maximum concurrency.
    """

    # System prompt for the LLM when handling general queries
    SYSTEM_PROMPT = (
        "You are a helpful and friendly customer support voice agent. "
        "You assist callers with order status inquiries and general questions. "
        "Keep your responses concise (1-3 sentences) since they will be spoken aloud. "
        "Be warm, professional, and direct. Do not use markdown or special formatting. "
        "If you have order information, present it clearly."
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

    # -------------------------------------------------------------------------
    # Main pipeline: audio bytes → response audio file
    # -------------------------------------------------------------------------
    async def process_audio(
        self,
        audio_bytes: bytes,
        call_sid: Optional[str] = None,
        is_mulaw: bool = True,
    ) -> dict:
        """
        Run the full pipeline on raw audio input.

        Args:
            audio_bytes: Raw audio bytes (μ-law 8kHz from Twilio, or PCM).
            call_sid: Twilio Call SID (if from a real call).
            is_mulaw: True if audio is μ-law encoded (Twilio format).

        Returns:
            dict with keys: transcript, intent, reply_text, audio_url, audio_path, stages
        """
        stages = []
        result = {
            "transcript": "",
            "intent": "unknown",
            "customer": None,
            "order": None,
            "reply_text": "",
            "audio_url": "",
            "audio_path": "",
            "stages": stages,
        }

        try:
            # -----------------------------------------------------------------
            # Stage 1: Convert audio to WAV for Groq
            # -----------------------------------------------------------------
            stages.append({"stage": "audio_prep", "status": "running", "ts": _now()})
            if is_mulaw:
                pcm_data = mulaw_to_pcm(audio_bytes)
                pcm_16k = resample_to_16khz(pcm_data)
                final_audio_bytes = build_wav(pcm_16k, sample_rate=16000)
                ext = "wav"
            else:
                # Browser sends webm/ogg blob, do not wrap in WAV header!
                final_audio_bytes = audio_bytes
                ext = "webm"

            # Save input audio locally for debugging
            input_file_id = call_sid or str(uuid.uuid4())[:8]
            input_filename = f"input_{input_file_id}_{int(datetime.now().timestamp())}.{ext}"
            input_filepath = AUDIO_CACHE_DIR / input_filename
            input_filepath.write_bytes(final_audio_bytes)
            input_audio_url = f"{settings.SERVER_HOST}/audio/{input_filename}"
            result["input_audio_url"] = input_audio_url

            stages[-1]["status"] = "done"
            stages[-1]["detail"] = f"Saved {len(final_audio_bytes)} bytes {ext.upper()} → {input_filename}"

            # -----------------------------------------------------------------
            # Stage 2: Speech-to-Text
            # -----------------------------------------------------------------
            stages.append({"stage": "stt", "status": "running", "ts": _now()})
            transcript = await self.groq.speech_to_text(final_audio_bytes, ext=ext)
            result["transcript"] = transcript
            stages[-1]["status"] = "done"
            stages[-1]["detail"] = transcript

            if not transcript:
                result["reply_text"] = "I'm sorry, I couldn't understand what you said. Could you please repeat that?"
                stages.append({"stage": "error", "status": "done", "detail": "Empty transcript"})
                await self._generate_and_save_audio(result, call_sid)
                return result

            # -----------------------------------------------------------------
            # Stage 3: Intent detection + data extraction
            # -----------------------------------------------------------------
            stages.append({"stage": "intent", "status": "running", "ts": _now()})
            intent, extracted = self._detect_intent(transcript)
            result["intent"] = intent
            stages[-1]["status"] = "done"
            stages[-1]["detail"] = f"intent={intent}, extracted={extracted}"

            # -----------------------------------------------------------------
            # Stage 4: Database lookup (if order query)
            # -----------------------------------------------------------------
            if intent == "order_status" and extracted.get("name"):
                stages.append({"stage": "db_lookup", "status": "running", "ts": _now()})

                dob = extracted.get("dob", "")
                customer = await self.db.verify_customer(extracted["name"], dob)
                result["customer"] = _serialize_customer(customer)

                if customer:
                    orders = await self.db.get_all_orders(customer["id"])
                    result["orders"] = orders
                    stages[-1]["status"] = "done"
                    stages[-1]["detail"] = f"customer={customer['full_name']}, orders={len(orders)}"
                else:
                    stages[-1]["status"] = "done"
                    stages[-1]["detail"] = "Customer not found"

            # -----------------------------------------------------------------
            # Stage 5: Generate reply text (LLM or template)
            # -----------------------------------------------------------------
            stages.append({"stage": "llm", "status": "running", "ts": _now()})
            reply_text = await self._generate_reply(result, transcript)
            result["reply_text"] = reply_text
            stages[-1]["status"] = "done"
            stages[-1]["detail"] = reply_text

            # -----------------------------------------------------------------
            # Stage 6: Text-to-Speech
            # -----------------------------------------------------------------
            await self._generate_and_save_audio(result, call_sid)

            return result

        except Exception as e:
            logger.exception(f"Pipeline error: {e}")
            stages.append({"stage": "error", "status": "failed", "detail": str(e)})
            result["reply_text"] = "I'm sorry, I encountered an error processing your request. Please try again."
            try:
                await self._generate_and_save_audio(result, call_sid)
            except Exception:
                pass
            return result

    # -------------------------------------------------------------------------
    # Simulate pipeline from text (for local testing UI)
    # -------------------------------------------------------------------------
    async def process_text_query(
        self,
        name: str,
        dob: str,
        query: str,
    ) -> dict:
        """
        Run the pipeline from a text query (skips STT).
        Used by the local testing UI.

        Args:
            name: Customer name.
            dob: Date of birth (YYYY-MM-DD).
            query: The user's text query.

        Returns:
            Same result dict as process_audio.
        """
        stages = []
        result = {
            "transcript": query,
            "intent": "order_status",
            "customer": None,
            "order": None,
            "reply_text": "",
            "audio_url": "",
            "audio_path": "",
            "stages": stages,
        }

        try:
            # DB lookup
            stages.append({"stage": "db_lookup", "status": "running", "ts": _now()})
            customer = await self.db.verify_customer(name, dob)
            result["customer"] = _serialize_customer(customer)

            if customer:
                orders = await self.db.get_all_orders(customer["id"])
                result["orders"] = orders
                stages[-1]["status"] = "done"
                stages[-1]["detail"] = f"Found customer: {customer['full_name']}, orders={len(orders)}"
            else:
                stages[-1]["status"] = "done"
                stages[-1]["detail"] = "Customer not found"

            # Generate reply
            stages.append({"stage": "llm", "status": "running", "ts": _now()})
            reply_text = await self._generate_reply(result, query)
            result["reply_text"] = reply_text
            stages[-1]["status"] = "done"
            stages[-1]["detail"] = reply_text

            # TTS
            await self._generate_and_save_audio(result, call_sid=None)

            return result

        except Exception as e:
            logger.exception(f"Text pipeline error: {e}")
            stages.append({"stage": "error", "status": "failed", "detail": str(e)})
            result["reply_text"] = "I'm sorry, I encountered an error. Please try again."
            try:
                await self._generate_and_save_audio(result, call_sid=None)
            except Exception:
                pass
            return result

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _detect_intent(self, text: str) -> tuple[str, dict]:
        """
        Simple keyword-based intent detection and entity extraction.

        Returns:
            (intent_name, extracted_entities_dict)
        """
        text_lower = text.lower()
        extracted = {}

        # Check for order-related keywords
        order_keywords = ["order", "status", "shipping", "delivery", "track", "package", "shipped"]
        is_order_query = any(kw in text_lower for kw in order_keywords)

        # Try to extract name — allow single or multiple words with simple cleanup
        name = self._extract_name(text)
        if name:
            extracted["name"] = name

        # Try to extract DOB — various date formats
        month_name = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        dob_patterns = [
            # "born May 15, 1990" or "born on May 15 1990"
            r"born\s+(?:on\s+)?(\w+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
            # "born 15 May 1990" or "born on 15 May, 1990"
            rf"born\s+(?:on\s+)?(\d{{1,2}}(?:st|nd|rd|th)?\s+{month_name}\s+\d{{4}})",
            # "date of birth is 1990-05-15"
            r"(?:date of birth|dob|d\.o\.b\.?)\s+(?:is\s+)?(\d{4}-\d{2}-\d{2})",
            # "dob 05/15/1990" or "dob 5-15-1990"
            r"(?:date of birth|dob|d\.o\.b\.?)\s+(?:is\s+)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
            # "born 05/15/1990" or "born 5-15-1990"
            r"born\s+(?:on\s+)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        ]
        for pattern in dob_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted["dob"] = _parse_date_string(match.group(1))
                break

        if "dob" not in extracted:
            # Fallback: look for common date phrases even without a DOB keyword
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

    async def _generate_reply(self, result: dict, user_text: str) -> str:
        """
        Generate the reply text using LLM with context from DB results.
        """
        customer = result.get("customer")
        orders = result.get("orders", [])

        # Build context for the LLM
        context_parts = []
        if customer:
            context_parts.append(
                f"The customer has been verified: {customer.get('full_name', 'Unknown')}."
            )
        else:
            context_parts.append(
                "The customer could not be found in our database."
            )

        if orders:
            orders_str = "\n".join(
                f"- Order #{o['order_number']}, Status: {o['status']}, "
                f"ETA: {o.get('estimated_arrival', 'N/A')}, Items: {o.get('items_summary', 'N/A')}"
                for o in orders
            )
            context_parts.append(f"Orders found:\n{orders_str}")
        else:
            if customer:
                context_parts.append("No orders were found for this customer.")

        context = " ".join(context_parts)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "system",
                "content": f"Customer/Order context: {context}",
            },
            {"role": "user", "content": user_text},
        ]

        try:
            reply = await self.groq.chat_completion(messages, stream=True)
            return reply
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            if orders:
                return (
                    f"You have {len(orders)} orders on file. Your latest order {orders[0]['order_number']} is currently {orders[0]['status']}. "
                    f"The estimated arrival date is {orders[0].get('estimated_arrival', 'not available')}."
                )
            elif customer:
                return "I found your account, but there are no recent orders on file."
            else:
                return "I wasn't able to find an account matching that information. Please verify your name and date of birth."

    async def _generate_and_save_audio(self, result: dict, call_sid: Optional[str]):
        """Generate TTS audio and save to cache."""
        reply_text = result.get("reply_text", "")
        if not reply_text:
            return

        stages = result.get("stages", [])
        stages.append({"stage": "tts", "status": "running", "ts": _now()})

        try:
            audio_bytes = await self.groq.text_to_speech(reply_text)

            # Generate unique filename
            file_id = call_sid or str(uuid.uuid4())[:8]
            filename = f"{file_id}_{int(datetime.now().timestamp())}.wav"
            filepath = AUDIO_CACHE_DIR / filename

            filepath.write_bytes(audio_bytes)

            audio_url = f"{settings.SERVER_HOST}/audio/{filename}"
            result["audio_url"] = audio_url
            result["audio_path"] = str(filepath)
            stages[-1]["status"] = "done"
            stages[-1]["detail"] = f"Saved {len(audio_bytes)} bytes → {filename}"

            logger.info(f"TTS audio saved: {filepath} ({len(audio_bytes)} bytes)")

            # If this is a real Twilio call, redirect it to play the audio
            if call_sid:
                await self.twilio.update_call_with_audio(call_sid, audio_url)

        except Exception as e:
            logger.error(f"TTS/save error: {e}")
            stages[-1]["status"] = "failed"
            stages[-1]["detail"] = str(e)


# =============================================================================
# Utility functions
# =============================================================================

def _now() -> str:
    """Current timestamp as ISO string."""
    return datetime.now().isoformat()


def _parse_date_string(date_str: str) -> str:
    """
    Parse various date formats into YYYY-MM-DD.

    Supports:
        "May 15, 1990"
        "1990-05-15"
        "05/15/1990"
        "5-15-1990"
    """
    date_str = date_str.strip().rstrip(",")
    date_str = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", date_str, flags=re.IGNORECASE)

    # Already ISO format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # "May 15, 1990" or "May 15 1990"
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # "15 May 1990" or "15 May, 1990"
    for fmt in ("%d %B %Y", "%d %B, %Y", "%d %b %Y", "%d %b, %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # "05/15/1990" or "5/15/1990"
    match = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", date_str)
    if match:
        month, day, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    # "1990/05/15" or "1990-5-15"
    match = re.match(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", date_str)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    return date_str  # Return as-is if no pattern matched


def _serialize_customer(customer: Optional[dict]) -> Optional[dict]:
    """Ensure customer dict is JSON-serializable."""
    if not customer:
        return None
    result = dict(customer)
    if "date_of_birth" in result and hasattr(result["date_of_birth"], "isoformat"):
        result["date_of_birth"] = result["date_of_birth"].isoformat()
    return result
