"""
Voice pipeline orchestrator — ties STT, LLM, database, and TTS together.

This is the central processing engine: given raw audio or text input,
it runs the full pipeline and produces an audio response.
"""

import logging
import os
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from app.groq_client import GroqClient
from app.database import DatabaseClient
from app.llm.rephrase import LLMRephraser
from app.logging.logger import log_event
from app.services.agent_service import AgentService
from app.twilio_handler import TwilioHandler
from app.audio_utils import build_wav, resample_to_16khz, mulaw_to_pcm
from app.channels.base import ChannelAdapter

logger = logging.getLogger(__name__)

# --- Environment Variables ---
SERVER_HOST = os.getenv("SERVER_HOST", "http://localhost:8000")


# Directory to cache generated TTS audio files
AUDIO_CACHE_DIR = Path("audio_cache")
AUDIO_CACHE_DIR.mkdir(exist_ok=True)


class VoicePipeline:
    """
    Orchestrates the full voice agent pipeline:
        Audio → STT → Conversation Orchestration → (Optional LLM Rephrase) → TTS

    Each stage is async for maximum concurrency.
    """

    def __init__(
        self,
        groq_client: GroqClient,
        db_client: DatabaseClient,
        twilio_handler: TwilioHandler,
        agent_service: AgentService,
        rephraser: LLMRephraser,
    ):
        self.groq = groq_client
        self.db = db_client
        self.twilio = twilio_handler
        self.agent = agent_service
        self.rephraser = rephraser

    # -------------------------------------------------------------------------
    # Main pipeline: audio bytes → response audio file
    # -------------------------------------------------------------------------
    async def process_audio(
        self,
        audio_bytes: bytes,
        call_sid: Optional[str] = None,
        is_mulaw: bool = True,
        channel_adapter: Optional[ChannelAdapter] = None,
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
            "session_id": call_sid or str(uuid.uuid4())[:8],
            "transcript": "",
            "intent": "unknown",
            "customer": None,
            "order": None,
            "reply_text": "",
            "audio_url": "",
            "audio_path": "",
            "state": "",
            "verified": False,
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
            input_filename = f"input_{input_file_id}_{int(datetime.now(UTC).timestamp())}.{ext}"
            input_filepath = AUDIO_CACHE_DIR / input_filename
            input_filepath.write_bytes(final_audio_bytes)
            input_audio_url = f"{SERVER_HOST}/audio/{input_filename}"
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
            # Stage 3: Deterministic conversation handling
            # -----------------------------------------------------------------
            stages.append({"stage": "conversation", "status": "running", "ts": _now()})
            conversation = await self.agent.handle_user_text(result["session_id"], transcript)
            result["intent"] = conversation.intent
            result["reply_text"] = conversation.reply_text
            result["customer"] = _serialize_customer(conversation.customer)
            result["orders"] = conversation.orders
            result["state"] = conversation.state
            result["verified"] = conversation.verified
            stages[-1]["status"] = "done"
            stages[-1]["detail"] = f"intent={conversation.intent}, state={conversation.state}"

            # -----------------------------------------------------------------
            # Stage 4: Optional LLM rephrase
            # -----------------------------------------------------------------
            if self.rephraser and self.rephraser.enabled:
                stages.append({"stage": "llm", "status": "running", "ts": _now()})
                rephrased = await self.rephraser.rephrase_text(result["reply_text"])
                result["reply_text"] = rephrased or result["reply_text"]
                stages[-1]["status"] = "done"
                stages[-1]["detail"] = result["reply_text"]

            # -----------------------------------------------------------------
            # Stage 6: Text-to-Speech
            # -----------------------------------------------------------------
            await self._generate_and_save_audio(result, call_sid)

            log_event(
                "pipeline_complete",
                session_id=result.get("session_id"),
                intent=result.get("intent"),
                state=result.get("state"),
                verified=result.get("verified"),
            )

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
            "session_id": str(uuid.uuid4())[:8],
            "transcript": query,
            "intent": "order_status",
            "customer": None,
            "order": None,
            "reply_text": "",
            "audio_url": "",
            "audio_path": "",
            "state": "",
            "verified": False,
            "stages": stages,
        }

        try:
            composite_query = f"My name is {name} and DOB is {dob}. {query}".strip()

            stages.append({"stage": "conversation", "status": "running", "ts": _now()})
            conversation = await self.agent.handle_user_text(result["session_id"], composite_query)
            result["intent"] = conversation.intent
            result["reply_text"] = conversation.reply_text
            result["customer"] = _serialize_customer(conversation.customer)
            result["orders"] = conversation.orders
            result["state"] = conversation.state
            result["verified"] = conversation.verified
            stages[-1]["status"] = "done"
            stages[-1]["detail"] = f"intent={conversation.intent}, state={conversation.state}"

            if self.rephraser and self.rephraser.enabled:
                stages.append({"stage": "llm", "status": "running", "ts": _now()})
                rephrased = await self.rephraser.rephrase_text(result["reply_text"])
                result["reply_text"] = rephrased or result["reply_text"]
                stages[-1]["status"] = "done"
                stages[-1]["detail"] = result["reply_text"]

            # TTS
            await self._generate_and_save_audio(result, call_sid=None)

            log_event(
                "pipeline_complete",
                session_id=result.get("session_id"),
                intent=result.get("intent"),
                state=result.get("state"),
                verified=result.get("verified"),
            )

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
            filename = f"output_{file_id}_{int(datetime.now(UTC).timestamp())}.wav"
            filepath = AUDIO_CACHE_DIR / filename

            filepath.write_bytes(audio_bytes)

            audio_url = f"{SERVER_HOST}/audio/{filename}"
            result["audio_url"] = audio_url
            result["audio_path"] = str(filepath)
            stages[-1]["status"] = "done"
            stages[-1]["detail"] = f"Saved {len(audio_bytes)} bytes → {filename}"

            logger.info(f"TTS audio saved: {filepath} ({len(audio_bytes)} bytes)")

            # If this is a real call, redirect it to play the audio via channel adapter
            if channel_adapter:
                await channel_adapter.send_audio_url(audio_url)
            elif call_sid and self.twilio:
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
    return datetime.now(UTC).isoformat()


def _serialize_customer(customer: Optional[dict]) -> Optional[dict]:
    """Ensure customer dict is JSON-serializable."""
    if not customer:
        return None
    result = dict(customer)
    if "date_of_birth" in result and hasattr(result["date_of_birth"], "isoformat"):
        result["date_of_birth"] = result["date_of_birth"].isoformat()
    return result
