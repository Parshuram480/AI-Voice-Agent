"""
Silero VAD wrapper — neural voice activity detection.

Uses custom Python wrapper with onnxruntime (no PyTorch dependency) for
frame-by-frame speech probability estimation. Falls back gracefully if not installed.

Silero VAD expects:
  - 16 kHz mono audio
  - 32ms frames (512 samples of float32)
  - Audio normalized to [-1.0, 1.0]
"""

import logging
import struct
import os
import ssl
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import numpy as np
    import onnxruntime as ort
    _SILERO_AVAILABLE = True
except ImportError:
    _SILERO_AVAILABLE = False


class _SileroVAD:
    """Custom pure-Python wrapper for Silero VAD using onnxruntime."""
    def __init__(self, sample_rate: int = 16000):
        if sample_rate not in (8000, 16000):
            raise ValueError("Silero VAD only supports 8000 or 16000 Hz sample rates.")
            
        self.sample_rate = sample_rate
        self.sr_array = np.array(sample_rate, dtype=np.int64)
        
        # Determine model path
        self.model_path = os.path.join(os.path.dirname(__file__), "silero_vad.onnx")
        
        # Download if missing
        if not os.path.exists(self.model_path):
            self._download_model()
            
        # Load ONNX session
        self.session = ort.InferenceSession(self.model_path)
        
        # Initialize state (shape: 2, 1, 128)
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        
    def _download_model(self):
        url = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
        logger.info(f"Downloading Silero VAD ONNX model from {url}...")
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        try:
            urllib.request.urlretrieve(url, self.model_path)
        except Exception as e:
            logger.warning(f"Standard download failed ({e}). Retrying with unverified SSL context...")
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(url, context=ctx) as response, open(self.model_path, 'wb') as out_file:
                out_file.write(response.read())
        logger.info(f"Successfully downloaded Silero VAD ONNX model to {self.model_path}")
        
    def process(self, float_bytes: bytes) -> float:
        # Convert float_bytes (raw float32) directly to numpy array
        audio_chunk = np.frombuffer(float_bytes, dtype=np.float32).reshape(1, -1)
        
        # Run model
        outputs = self.session.run(None, {
            "input": audio_chunk,
            "state": self.state,
            "sr": self.sr_array
        })
        
        self.state = outputs[1]
        return float(outputs[0][0][0])


def is_silero_available() -> bool:
    """Check if onnxruntime and numpy are installed."""
    return _SILERO_AVAILABLE


class SileroVoiceDetector:
    """
    Frame-level speech detector using Silero VAD (neural network).

    Accepts 16-bit PCM frames and returns a speech probability [0.0, 1.0].
    Much more robust against background noise than WebRTC VAD.
    """

    # Silero requires exactly 32ms frames at 16kHz = 512 samples
    FRAME_SAMPLES = 512
    FRAME_BYTES = FRAME_SAMPLES * 2  # 16-bit = 2 bytes per sample

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5):
        """
        Args:
            sample_rate: Audio sample rate (must be 8000 or 16000).
            threshold: Speech probability threshold (0.0–1.0).
                       Higher = more aggressive noise rejection.
        """
        if not _SILERO_AVAILABLE:
            raise RuntimeError(
                "onnxruntime/numpy are not installed. "
                "Install them with: pip install onnxruntime numpy"
            )

        self._model = _SileroVAD(sample_rate)
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._buffer = bytearray()
        logger.info(
            f"Silero VAD initialized (sample_rate={sample_rate}, "
            f"threshold={threshold})"
        )

    def get_speech_probability(self, pcm_frame: bytes) -> float:
        """
        Get speech probability for a single 32ms PCM frame.

        Args:
            pcm_frame: Exactly 1024 bytes of 16-bit PCM (512 samples at 16kHz).

        Returns:
            Float probability in [0.0, 1.0].
        """
        # Convert 16-bit PCM to float32 normalized to [-1, 1]
        num_samples = len(pcm_frame) // 2
        samples = struct.unpack(f"<{num_samples}h", pcm_frame)
        float_samples = [s / 32768.0 for s in samples]

        # Pack as float32 bytes for silero
        float_bytes = struct.pack(f"<{num_samples}f", *float_samples)

        try:
            prob = self._model.process(float_bytes)
            return float(prob)
        except Exception as e:
            logger.error(f"Silero VAD process error: {e}")
            return 0.0

    def is_speech(self, pcm_frame: bytes) -> bool:
        """
        Check if a PCM frame contains speech.

        Args:
            pcm_frame: 16-bit PCM bytes. If not exactly 32ms, will be
                       buffered internally and processed when enough data
                       accumulates.

        Returns:
            True if speech is detected above the threshold.
        """
        self._buffer.extend(pcm_frame)

        # Process all complete 32ms frames in the buffer
        max_prob = 0.0
        while len(self._buffer) >= self.FRAME_BYTES:
            frame = bytes(self._buffer[:self.FRAME_BYTES])
            self._buffer = self._buffer[self.FRAME_BYTES:]
            prob = self.get_speech_probability(frame)
            max_prob = max(max_prob, prob)

        return max_prob >= self._threshold

    def reset(self):
        """Reset internal state for a new utterance."""
        self._buffer.clear()
        # Re-initialize model state
        self._model = _SileroVAD(self._sample_rate)
