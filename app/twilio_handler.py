"""
Twilio handler — TwiML generation and call management.

Generates XML responses for Twilio webhooks and provides helpers
to update live calls with audio playback.
"""

import json

import logging
from typing import Optional

from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Start, Connect

from app.config import settings

logger = logging.getLogger(__name__)


class TwilioHandler:
    """
    Manages Twilio TwiML generation and REST API interactions.
    """

    def __init__(self):
        """Initialize the Twilio REST client (used for call updates)."""
        self._client: Optional[TwilioClient] = None
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            self._client = TwilioClient(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
            )
            logger.info("Twilio REST client initialized.")
        else:
            logger.warning("Twilio credentials not set — call updates will be unavailable.")

    # -------------------------------------------------------------------------
    # TwiML Generation
    # -------------------------------------------------------------------------
    def generate_stream_twiml(self, ws_url: str) -> str:
        """
        Generate TwiML that starts a media stream and greets the caller.

        The stream sends real-time audio to our WebSocket endpoint.
        A long pause keeps the call alive while we process.

        Args:
            ws_url: Full WebSocket URL (e.g. "wss://example.ngrok.app/audio-stream").

        Returns:
            TwiML XML string.
        """
        response = VoiceResponse()

        # Start streaming audio to our WebSocket
        start = Start()
        start.stream(url=ws_url)
        response.append(start)

        # Greet the caller
        response.say(
            "Hello! Welcome to our order support line. "
            "Please state your name, date of birth, and your query. "
            "For example: My name is John Smith, born May 15, 1990. What is my order status?",
            voice="alice",
        )

        # Keep the call alive while we process (up to 60 seconds)
        response.pause(length=60)

        twiml = str(response)
        logger.info(f"Generated stream TwiML: {twiml[:200]}...")
        return twiml

    def generate_play_twiml(self, audio_url: str) -> str:
        """
        Generate TwiML to play an audio file and hang up.

        Args:
            audio_url: Public URL of the WAV file to play.

        Returns:
            TwiML XML string.
        """
        response = VoiceResponse()
        response.play(audio_url)
        response.hangup()
        return str(response)

    # -------------------------------------------------------------------------
    # Call Management
    # -------------------------------------------------------------------------
    async def update_call_with_audio(self, call_sid: str, audio_url: str) -> bool:
        """
        Redirect a live Twilio call to play an audio file.

        Uses the Twilio REST API to update the call's TwiML.

        Args:
            call_sid: The Twilio Call SID.
            audio_url: Public URL of the WAV file to play.

        Returns:
            True if the update succeeded, False otherwise.
        """
        if not self._client:
            logger.error("Cannot update call — Twilio client not initialized.")
            return False

        try:
            twiml = self.generate_play_twiml(audio_url)
            self._client.calls(call_sid).update(twiml=twiml)
            logger.info(f"Updated call {call_sid} to play {audio_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to update call {call_sid}: {e}")
            return False

    async def send_audio_to_stream(
        self,
        websocket,
        pcm_audio: bytes,
        stream_sid: str,
    ) -> bool:
        """
        Send audio back through a Twilio bidirectional media stream.

        Converts PCM to μ-law and sends as base64 media message.
        This enables truly low-latency in-call audio playback
        without needing a separate HTTP audio URL.

        Args:
            websocket: The active Twilio WebSocket connection.
            pcm_audio: Raw 16-bit PCM audio bytes.
            stream_sid: The Twilio Stream SID.

        Returns:
            True if the send succeeded, False otherwise.

        Note:
            Not yet wired into the main pipeline — available for future use.
        """
        import base64
        from app.audio_utils import pcm_to_mulaw

        try:
            mulaw_audio = pcm_to_mulaw(pcm_audio)
            payload = base64.b64encode(mulaw_audio).decode("ascii")

            message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": payload,
                },
            }
            await websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Failed to send audio to stream {stream_sid}: {e}")
            return False
