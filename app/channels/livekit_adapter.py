import asyncio
import logging
import audioop
from livekit import rtc
from app.channels.base import ChannelAdapter
from app.audio_utils import wav_bytes_to_pcm, to_mono, resample_pcm

logger = logging.getLogger(__name__)

class LiveKitChannelAdapter(ChannelAdapter):
    """
    Adapter to route outbound audio and clear events to a LiveKit WebRTC session.
    """

    def __init__(self, audio_source: rtc.AudioSource, sample_rate: int = 24000):
        self.audio_source = audio_source
        self.sample_rate = sample_rate
        self.is_cleared = asyncio.Event()

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """
        Sends raw audio chunks to the LiveKit AudioSource.
        Paces transmission in 10ms steps to match real-time WebRTC playback pacing.
        """
        try:
            # Parse WAV if it has RIFF header
            if pcm_bytes.startswith(b"RIFF"):
                pcm_data, sample_rate, sample_width, channels = wav_bytes_to_pcm(pcm_bytes)
            else:
                # Default to Cartesia raw PCM 24000Hz mono 16-bit
                pcm_data = pcm_bytes
                sample_rate = 24000
                sample_width = 2
                channels = 1

            if not pcm_data:
                return

            target_sample_rate = self.sample_rate
            target_channels = 1
            target_sample_width = 2

            # Ensure 16-bit depth
            if sample_width != target_sample_width:
                pcm_data = audioop.lin2lin(pcm_data, sample_width, target_sample_width)
                sample_width = target_sample_width

            # Convert to mono
            if channels != target_channels:
                pcm_data = to_mono(pcm_data, sample_width=sample_width, channels=channels)
                channels = target_channels

            # Resample to the target AudioSource rate if necessary
            if sample_rate != target_sample_rate:
                pcm_data = resample_pcm(
                    pcm_data,
                    in_rate=sample_rate,
                    out_rate=target_sample_rate,
                    sample_width=sample_width,
                    channels=channels
                )

            # 10ms chunk size in bytes
            # target_sample_rate * target_sample_width * target_channels * 10 / 1000
            # E.g., for 24kHz: 24000 * 2 * 1 * 0.01 = 480 bytes
            bytes_per_sample = target_sample_width * target_channels
            samples_per_10ms = target_sample_rate // 100
            chunk_size = samples_per_10ms * bytes_per_sample

            self.is_cleared.clear()

            for i in range(0, len(pcm_data), chunk_size):
                if self.is_cleared.is_set():
                    logger.info("LiveKit outbound audio transmission canceled by clear event.")
                    break

                chunk = pcm_data[i:i+chunk_size]
                if len(chunk) < chunk_size:
                    # Pad trailing frame with silence
                    chunk = chunk + b"\x00" * (chunk_size - len(chunk))

                frame = rtc.AudioFrame(
                    data=chunk,
                    sample_rate=target_sample_rate,
                    num_channels=target_channels,
                    samples_per_channel=samples_per_10ms
                )

                # Capture frame into LiveKit audio source
                await self.audio_source.capture_frame(frame)
                
                # Pace sending to match 10ms playback duration
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error(f"LiveKitChannelAdapter failed to send audio: {e}")

    async def send_clear(self) -> None:
        """
        Stop outbound audio transmission immediately.
        """
        logger.info("LiveKitChannelAdapter: send_clear() triggered.")
        self.is_cleared.set()

    @property
    def channel_type(self) -> str:
        return "livekit"
