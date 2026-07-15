import logging
import audioop
from app.channels.base import ChannelAdapter
from app.twilio_handler import TwilioHandler
from app.audio_utils import wav_bytes_to_pcm, to_mono, pcm_to_mulaw

logger = logging.getLogger(__name__)

class TwilioChannelAdapter(ChannelAdapter):
    """
    Adapter to route outbound audio and clear events to Twilio.
    """

    def __init__(self, twilio_handler: TwilioHandler, websocket, stream_sid: str, call_sid: str):
        self.twilio = twilio_handler
        self.websocket = websocket
        self.stream_sid = stream_sid
        self.call_sid = call_sid
        self.resample_state = None

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """
        Expects raw PCM or WAV data, normalizes it to μ-law 8kHz mono, and transmits it.
        """
        if not self.stream_sid or not self.websocket:
            return

        try:
            # Detect format and extract raw PCM
            if pcm_bytes.startswith(b"RIFF"):
                pcm_data, sample_rate, sample_width, channels = wav_bytes_to_pcm(pcm_bytes)
            else:
                # Default to Cartesia raw PCM 24kHz, 16-bit, mono
                pcm_data = pcm_bytes
                sample_rate = 24000
                sample_width = 2
                channels = 1

            if not pcm_data:
                return

            # Normalize to 16-bit
            if sample_width != 2:
                pcm_data = audioop.lin2lin(pcm_data, sample_width, 2)
                sample_width = 2

            # Force mono channel
            pcm_data = to_mono(pcm_data, sample_width=sample_width, channels=channels)

            # Resample to 8000 Hz for Twilio
            if sample_rate != 8000:
                pcm_data, self.resample_state = audioop.ratecv(
                    pcm_data,
                    sample_width,
                    1,
                    sample_rate,
                    8000,
                    self.resample_state,
                )

            # Send to Twilio Media Stream
            await self.twilio.send_audio_to_stream(self.websocket, pcm_data, self.stream_sid)

        except Exception as e:
            logger.error(f"TwilioChannelAdapter failed to send audio: {e}")

    async def send_clear(self) -> None:
        """
        Send a clear command to immediately flush Twilio's audio buffers.
        """
        if self.websocket and self.stream_sid:
            await self.twilio.clear_stream(self.websocket, self.stream_sid)

    async def send_audio_url(self, audio_url: str) -> bool:
        """
        Update call with audio URL if call SID is available.
        """
        if self.call_sid:
            return await self.twilio.update_call_with_audio(self.call_sid, audio_url)
        return False

    @property
    def channel_type(self) -> str:
        return "twilio"
