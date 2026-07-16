"""
Twilio handler — TwiML generation and call management.

Generates XML responses for Twilio webhooks and provides helpers
to update live calls with audio playback.
"""

import json

import logging
import os
from typing import Optional

from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Start, Connect


logger = logging.getLogger(__name__)

# --- Environment Variables ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")



class TwilioHandler:
    """
    Manages Twilio TwiML generation and REST API interactions.
    """

    def __init__(self):
        """Initialize the Twilio REST client (used for call updates)."""
        self._client: Optional[TwilioClient] = None
        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            self._client = TwilioClient(
                TWILIO_ACCOUNT_SID,
                TWILIO_AUTH_TOKEN,
            )
            logger.info("Twilio REST client initialized.")
        else:
            logger.warning("Twilio credentials not set — call updates will be unavailable.")

    # -------------------------------------------------------------------------
    # TwiML Generation
    # -------------------------------------------------------------------------
    def generate_stream_twiml(self, ws_url: str) -> str:
        """
        Generate TwiML that connects a media stream.

        The stream sends real-time audio to our WebSocket endpoint
        and allows us to send audio back.

        Args:
            ws_url: Full WebSocket URL (e.g. "wss://example.ngrok.app/audio-stream").

        Returns:
            TwiML XML string.
        """
        from twilio.twiml.voice_response import Connect
        response = VoiceResponse()

        # Connect the call entirely to our WebSocket for bi-directional audio
        connect = Connect()
        connect.stream(url=ws_url)
        response.append(connect)

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
        import asyncio
        from app.audio_utils import pcm_to_mulaw

        try:
            # Initialize a lock on the websocket if it doesn't exist
            if not hasattr(websocket, "_send_lock"):
                websocket._send_lock = asyncio.Lock()
                
            mulaw_audio = pcm_to_mulaw(pcm_audio)
            payload = base64.b64encode(mulaw_audio).decode("ascii")

            message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": payload,
                },
            }
            
            logger.info(f"Sending {len(payload)} bytes of audio to Twilio (streamSid: {stream_sid})")
            
            # Use the lock to prevent concurrent frame corruption
            async with websocket._send_lock:
                await websocket.send_text(json.dumps(message))
                
            return True
        except Exception as e:
            logger.error(f"Failed to send audio to stream {stream_sid}: {e}")
            return False

    async def clear_stream(self, websocket, stream_sid: str) -> bool:
        """
        Send a clear event to Twilio to immediately stop playing buffered audio.
        This is used for barge-in interruptions.
        """
        import json
        import asyncio
        try:
            if not hasattr(websocket, "_send_lock"):
                websocket._send_lock = asyncio.Lock()
            
            message = {
                "event": "clear",
                "streamSid": stream_sid
            }
            logger.info(f"Sending clear command to Twilio (streamSid: {stream_sid})")
            
            async with websocket._send_lock:
                await websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Failed to send clear to stream {stream_sid}: {e}")
            return False

    async def make_outbound_call(self, to_number: str, client_id: int, server_host: str) -> str:
        """
        Initiates an outbound call to the given phone number.
        """
        if not self._client:
            raise ValueError("Twilio client is not initialized. Please check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")
        
        twilio_from = os.getenv("TWILIO_PHONE_NUMBER")
        if not twilio_from:
            raise ValueError("TWILIO_PHONE_NUMBER environment variable is not configured.")
        
        # Prioritize NGROK_URL environment variable if configured
        ngrok_url = os.getenv("NGROK_URL")
        if ngrok_url:
            if "/voice" in ngrok_url:
                callback_url = ngrok_url
                if "?" in callback_url:
                    callback_url += f"&client_id={client_id}"
                else:
                    callback_url += f"?client_id={client_id}"
            else:
                base_url = ngrok_url.rstrip("/")
                callback_url = f"{base_url}/voice?client_id={client_id}"
        else:
            base_url = server_host.rstrip("/")
            callback_url = f"{base_url}/voice?client_id={client_id}"
        
        logger.info(f"Triggering outbound call from {twilio_from} to {to_number} using webhook: {callback_url}")
        
        import anyio
        call = await anyio.to_thread.run_sync(
            lambda: self._client.calls.create(
                to=to_number,
                from_=twilio_from,
                url=callback_url,
                method="POST"
            )
        )
        logger.info(f"Outbound call successfully initiated. Call SID: {call.sid}")
        return call.sid

    async def get_call_status(self, call_sid: str) -> str:
        """
        Retrieves the status of a live or completed call from Twilio.
        """
        if not self._client:
            raise ValueError("Twilio client is not initialized.")
        
        import anyio
        call = await anyio.to_thread.run_sync(
            lambda: self._client.calls(call_sid).fetch()
        )
        return call.status

    async def end_call(self, call_sid: str) -> bool:
        """
        Terminates a live Twilio call.
        """
        if not self._client:
            raise ValueError("Twilio client is not initialized.")
        
        import anyio
        try:
            await anyio.to_thread.run_sync(
                lambda: self._client.calls(call_sid).update(status="completed")
            )
            return True
        except Exception as e:
            logger.error(f"Failed to end call {call_sid}: {e}")
            return False
