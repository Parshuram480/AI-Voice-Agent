"""
Audio utility functions for the voice-agent pipeline.

Handles:
- ÃƒÆ’Ã…Â½Ãƒâ€šÃ‚Â¼-law (Twilio) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ linear PCM conversion
- Resampling 8 kHz ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ 16 kHz for Groq Whisper
- Building WAV byte buffers from raw PCM
- End-of-speech silence detection
"""

import audioop
import io
import struct
import wave
import logging

logger = logging.getLogger(__name__)

try:
    import webrtcvad
except ImportError:
    webrtcvad = None



def mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    """
    Decode ÃƒÆ’Ã…Â½Ãƒâ€šÃ‚Â¼-law encoded audio (from Twilio Media Streams) to 16-bit linear PCM.

    Twilio sends audio as 8-bit ÃƒÆ’Ã…Â½Ãƒâ€šÃ‚Â¼-law, 8 kHz, mono.
    Returns raw 16-bit signed PCM bytes.
    """
    return audioop.ulaw2lin(mulaw_bytes, 2)  # 2 = 16-bit samples


def resample_to_16khz(pcm_8khz: bytes) -> bytes:
    """
    Upsample 8 kHz mono PCM ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ 16 kHz mono PCM.

    Groq Whisper expects 16 kHz input for optimal accuracy.
    Uses audioop.ratecv for sample-rate conversion.
    """
    # ratecv params: (fragment, width, nchannels, inrate, outrate, state)
    converted, _ = audioop.ratecv(
        pcm_8khz,
        2,       # sample width: 16-bit
        1,       # mono
        8000,    # input rate
        16000,   # output rate
        None,    # no previous state
    )
    return converted


def build_wav(pcm_data: bytes, sample_rate: int = 16000, sample_width: int = 2, channels: int = 1) -> bytes:
    """
    Wrap raw PCM data in a valid WAV container.

    Args:
        pcm_data: Raw 16-bit signed PCM bytes.
        sample_rate: Sample rate in Hz (default 16000).
        sample_width: Bytes per sample (default 2 for 16-bit).
        channels: Number of audio channels (default 1 for mono).

    Returns:
        Complete WAV file as bytes, ready for Groq STT or playback.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def detect_silence(
    pcm_chunk: bytes,
    threshold: int = 500,
    sample_width: int = 2,
) -> bool:
    """
    Check if an audio chunk is silence (below amplitude threshold).

    Uses RMS (root mean square) energy of the chunk.

    Args:
        pcm_chunk: Raw 16-bit PCM audio bytes.
        threshold: RMS energy below this value is considered silence.
        sample_width: Bytes per sample (2 for 16-bit).

    Returns:
        True if the chunk is silence, False otherwise.
    """
    if not pcm_chunk:
        return True
    rms = audioop.rms(pcm_chunk, sample_width)
    return rms < threshold


def pcm_to_mulaw(pcm_bytes: bytes) -> bytes:
    """
    Encode 16-bit linear PCM to 8-bit ÃƒÆ’Ã…Â½Ãƒâ€šÃ‚Â¼-law.
    Useful for sending audio back through Twilio's media stream.
    """
    return audioop.lin2ulaw(pcm_bytes, 2)


def get_audio_duration_seconds(pcm_bytes: bytes, sample_rate: int = 16000, sample_width: int = 2) -> float:
    """Calculate duration in seconds of raw PCM audio."""
    if not pcm_bytes:
        return 0.0
    num_samples = len(pcm_bytes) / sample_width
    return num_samples / sample_rate


def compute_rms(pcm_chunk: bytes, sample_width: int = 2) -> int:
    """
    Compute the RMS (root mean square) energy of a PCM audio chunk.

    Returns:
        Integer RMS value.  Higher = louder.
    """
    if not pcm_chunk:
        return 0
    return audioop.rms(pcm_chunk, sample_width)


def trim_trailing_silence(
    pcm_data: bytes,
    threshold: int = 500,
    chunk_ms: int = 20,
    sample_rate: int = 16000,
    sample_width: int = 2,
) -> bytes:
    """
    Remove trailing silence from raw PCM audio.

    Walks backward in *chunk_ms* steps, trimming all silence below *threshold*.
    Keeps at least 200ms of audio to avoid over-trimming.

    Args:
        pcm_data: Raw 16-bit PCM bytes.
        threshold: RMS below this is silence.
        chunk_ms: Step size in milliseconds.
        sample_rate: Audio sample rate.
        sample_width: Bytes per sample.

    Returns:
        Trimmed PCM bytes.
    """
    chunk_bytes = int(sample_rate * sample_width * chunk_ms / 1000)
    min_bytes = int(sample_rate * sample_width * 0.2)  # keep ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°Ãƒâ€šÃ‚Â¥200ms

    end = len(pcm_data)
    while end > min_bytes:
        start_pos = max(0, end - chunk_bytes)
        chunk = pcm_data[start_pos:end]
        if audioop.rms(chunk, sample_width) >= threshold:
            break
        end = start_pos

    return pcm_data[:end] if end > 0 else pcm_data


def pcm_to_wav_header(
    data_size: int,
    sample_rate: int = 16000,
    sample_width: int = 2,
    channels: int = 1,
) -> bytes:
    """
    Generate a standalone WAV header (44 bytes) for a given PCM data size.

    Useful for prepending a header to raw PCM when building WAV on the fly.

    Args:
        data_size: Number of PCM data bytes that will follow.
        sample_rate: Sample rate in Hz.
        sample_width: Bytes per sample.
        channels: Number of channels.

    Returns:
        44-byte WAV/RIFF header.
    """
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    bits_per_sample = sample_width * 8

    header = struct.pack(
        "<4sI4s"   # RIFF header
        "4sIHHIIHH"  # fmt  sub-chunk
        "4sI",       # data sub-chunk header
        b"RIFF",
        36 + data_size,       # file size - 8
        b"WAVE",
        b"fmt ",
        16,                   # PCM format chunk size
        1,                    # PCM format tag
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header


def wav_bytes_to_pcm(wav_bytes: bytes) -> tuple[bytes, int, int, int]:
    """
    Extract raw PCM audio from WAV bytes.

    Returns:
        (pcm_bytes, sample_rate, sample_width, channels)
    """
    if not wav_bytes:
        return b"", 16000, 2, 1

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        pcm_bytes = wf.readframes(wf.getnframes())

    return pcm_bytes, sample_rate, sample_width, channels


def to_mono(pcm_bytes: bytes, sample_width: int = 2, channels: int = 1) -> bytes:
    """Convert multi-channel PCM to mono."""
    if channels <= 1:
        return pcm_bytes
    return audioop.tomono(pcm_bytes, sample_width, 0.5, 0.5)


def resample_pcm(
    pcm_bytes: bytes,
    in_rate: int,
    out_rate: int,
    sample_width: int = 2,
    channels: int = 1,
) -> bytes:
    """Resample PCM audio from in_rate to out_rate."""
    if not pcm_bytes or in_rate == out_rate:
        return pcm_bytes
    converted, _ = audioop.ratecv(
        pcm_bytes,
        sample_width,
        channels,
        in_rate,
        out_rate,
        None,
    )
    return converted

class FrameGenerator:
    """Generates audio frames of exactly `frame_duration_ms` from a byte buffer."""
    def __init__(self, frame_duration_ms: int = 30, sample_rate: int = 16000, sample_width: int = 2):
        self.frame_duration_ms = frame_duration_ms
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.frame_size = int(sample_rate * (frame_duration_ms / 1000.0) * sample_width)
        self.buffer = bytearray()

    def add_data(self, data: bytes):
        self.buffer.extend(data)

    def get_frames(self):
        """Yields available frames of exact size."""
        while len(self.buffer) >= self.frame_size:
            frame = bytes(self.buffer[:self.frame_size])
            self.buffer = self.buffer[self.frame_size:]
            yield frame

class VoiceActivityDetector:
    """
    Multi-engine voice activity detector.

    Priority chain:
      1. Silero VAD (neural, best noise rejection) — if USE_SILERO_VAD=true
      2. WebRTC VAD (rule-based, decent) — if webrtcvad is installed
      3. RMS energy threshold (basic fallback)
    """
    def __init__(
        self,
        aggressiveness: int = 2,
        sample_rate: int = 16000,
        fallback_threshold: int = 500,
        use_silero: bool = False,
        silero_threshold: float = 0.5,
    ):
        self.sample_rate = sample_rate
        self.fallback_threshold = fallback_threshold
        self._silero = None
        self._webrtc_vad = None
        self._engine = "rms"  # default

        # Try Silero first (if requested)
        if use_silero:
            try:
                from app.vad.silero_vad import SileroVoiceDetector, is_silero_available
                if is_silero_available():
                    self._silero = SileroVoiceDetector(
                        sample_rate=sample_rate,
                        threshold=silero_threshold,
                    )
                    self._engine = "silero"
                    logger.info("VAD engine: Silero (neural)")
                else:
                    logger.warning("Silero VAD requested but silero-vad-lite not installed.")
            except Exception as e:
                logger.warning(f"Silero VAD init failed: {e}. Falling back.")

        # Try WebRTC as second choice
        if self._engine != "silero" and webrtcvad:
            try:
                self._webrtc_vad = webrtcvad.Vad(aggressiveness)
                self._engine = "webrtc"
                logger.info(f"VAD engine: WebRTC (aggressiveness={aggressiveness})")
            except Exception as e:
                logger.warning(f"WebRTC VAD init failed: {e}. Using RMS fallback.")

        if self._engine == "rms":
            logger.warning("VAD engine: RMS energy (basic fallback)")

    @property
    def engine_name(self) -> str:
        """Return the name of the active VAD engine."""
        return self._engine

    def is_speech(self, pcm_frame: bytes) -> bool:
        """
        Check if the frame contains speech.

        Args:
            pcm_frame: Raw 16-bit PCM bytes.
                       For WebRTC: must be exactly 10, 20, or 30ms.
                       For Silero: any length (internally buffered to 32ms).

        Returns:
            True if speech is detected.
        """
        if self._silero:
            try:
                return self._silero.is_speech(pcm_frame)
            except Exception as e:
                logger.error(f"Silero VAD error: {e}. Falling back to RMS.")
                return not detect_silence(pcm_frame, self.fallback_threshold)

        if self._webrtc_vad:
            try:
                return self._webrtc_vad.is_speech(pcm_frame, self.sample_rate)
            except Exception as e:
                logger.error(f"WebRTC VAD error: {e}. Falling back to RMS.")
                return not detect_silence(pcm_frame, self.fallback_threshold)

        return not detect_silence(pcm_frame, self.fallback_threshold)

    def reset(self):
        """Reset VAD state (useful between utterances)."""
        if self._silero:
            self._silero.reset()


