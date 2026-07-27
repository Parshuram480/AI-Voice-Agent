import os
import asyncio
import logging
import wave
import random
from collections import deque
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Fallback voice if none is configured
DEFAULT_VOICE = "Aoede"
# We match Gemini Live output format
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2

# Domain-agnostic filler phrases
FILLER_PHRASES = {
    "verification": {
        "medium": [
            "One second.",
            "Checking.",
            "Just a moment.",
        ],
        "slow": [
            "Let me verify those details for you.",
            "I'm pulling up your file now.",
            "One moment while I confirm that.",
        ],
        "fast": []
    },
    "lookup": {
        "medium": [
            "Checking.",
            "One moment.",
            "Looking now.",
        ],
        "slow": [
            "Let me see what I can find.",
            "I'm checking that for you now.",
            "Give me just a second to look that up.",
        ],
        "fast": []
    },
    "thinking": {
        "medium": [
            "Hmm.",
            "Let's see.",
        ],
        "slow": [
            "Let me think about that.",
            "Good question, let me check.",
        ],
        "fast": []
    }
}

class FillerAudioService:
    def __init__(self, cache_dir: str = "data/audio_cache/fillers", cooldown_size: int = 3):
        self.cache_dir = Path(cache_dir)
        self.cooldown_size = cooldown_size
        
        # In-memory cache of PCM byte arrays
        # Format: self._cache[category][latency_type] = [pcm_bytes, pcm_bytes, ...]
        self._cache: dict[str, dict[str, list[bytes]]] = {}
        
        # Anti-repeat tracking
        # Format: self._recent_indices[category][latency_type] = deque()
        self._recent_indices: dict[str, dict[str, deque[int]]] = {}
        
        self.voice_name = os.getenv("GEMINI_VOICE", DEFAULT_VOICE)
        self.voice_cache_dir = self.cache_dir / self.voice_name
        self.is_ready = False

    async def initialize(self):
        """
        Loads cached clips from disk or generates them if missing.
        Should be called at server startup.
        """
        self.voice_cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initializing FillerAudioService for voice '{self.voice_name}'...")
        
        # Build structure
        for cat in FILLER_PHRASES:
            self._cache[cat] = {}
            self._recent_indices[cat] = {}
            for lat in FILLER_PHRASES[cat]:
                self._cache[cat][lat] = []
                self._recent_indices[cat][lat] = deque(maxlen=self.cooldown_size)
                
        # Generate or load
        tasks = []
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set. FillerAudioService disabled.")
            return

        client = genai.Client(api_key=api_key)

        for category, latencies in FILLER_PHRASES.items():
            for lat_type, phrases in latencies.items():
                if not phrases:
                    continue
                
                for i, phrase in enumerate(phrases):
                    filename = f"{category}_{lat_type}_{i}.wav"
                    filepath = self.voice_cache_dir / filename
                    
                    if filepath.exists():
                        # Load from disk
                        pcm_data = self._load_wav(filepath)
                        self._cache[category][lat_type].append(pcm_data)
                    else:
                        # Generate and save
                        tasks.append(self._generate_and_cache(client, category, lat_type, phrase, filepath))
        
        if tasks:
            logger.info(f"Generating {len(tasks)} missing filler clips via Gemini TTS...")
            # We don't parallelize too aggressively to avoid rate limits on startup
            for chunk in [tasks[i:i+5] for i in range(0, len(tasks), 5)]:
                results = await asyncio.gather(*chunk, return_exceptions=True)
                for r in results:
                    if isinstance(r, Exception):
                        logger.error(f"Failed to generate filler clip: {r}")
                await asyncio.sleep(1) # rate limit buffer
            
            logger.info(f"Finished generating clips.")
        else:
            logger.info("All filler clips loaded from disk cache.")
            
        self.is_ready = True

    async def _generate_and_cache(self, client, category: str, lat_type: str, phrase: str, filepath: Path):
        """Generates a single clip using Gemini TTS preview."""
        # Using the TTS preview model to guarantee identical voice profile
        model_name = "gemini-2.5-flash-preview-tts"
        
        try:
            # We use asyncio.to_thread because the genai client is synchronous in this usage
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=phrase,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice_name)
                        )
                    )
                )
            )
            
            audio_data = response.candidates[0].content.parts[0].inline_data.data
            
            # The TTS model returns a WAV file (including RIFF header). We need to extract the raw PCM.
            from app.audio_utils import wav_bytes_to_pcm
            try:
                pcm_data, _, _, _ = wav_bytes_to_pcm(audio_data)
            except Exception as e:
                logger.warning(f"Failed to extract PCM from TTS response (might already be raw PCM): {e}")
                pcm_data = audio_data
            
            # Save to disk as WAV (which wraps the raw PCM cleanly)
            await asyncio.to_thread(self._save_wav, filepath, pcm_data)
            
            # Save raw PCM to memory
            self._cache[category][lat_type].append(pcm_data)
        except Exception as e:
            logger.error(f"Error generating TTS for phrase '{phrase}': {e}")
            raise e

    def _save_wav(self, filepath: Path, pcm_data: bytes):
        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_data)

    def _load_wav(self, filepath: Path) -> bytes:
        with wave.open(str(filepath), "rb") as wf:
            return wf.readframes(wf.getnframes())

    def select_filler(self, category: str, latency_type: str) -> tuple[bytes, int] | None:
        """
        Returns a tuple of (pcm_bytes, sample_rate) for the requested category/latency.
        Returns None if fast latency or no clips exist.
        """
        if not self.is_ready or latency_type == "fast":
            return None
            
        if category not in self._cache or latency_type not in self._cache[category]:
            category = "thinking" # Fallback
            
        clips = self._cache.get(category, {}).get(latency_type, [])
        if not clips:
            # Fallback to thinking/medium
            clips = self._cache.get("thinking", {}).get("medium", [])
            category = "thinking"
            latency_type = "medium"
            if not clips:
                return None
                
        recent = self._recent_indices[category][latency_type]
        
        # Pick a non-recently-used clip
        available = [i for i in range(len(clips)) if i not in recent]
        if not available:
            available = list(range(len(clips))) # Reset if all on cooldown
            
        idx = random.choice(available)
        recent.append(idx)
        
        clip_data = clips[idx]
        return clip_data, SAMPLE_RATE

    def get_filler_metadata(self, category: str, latency_type: str) -> dict:
        """Helper to get text context for logging (what did we likely play?)"""
        try:
            phrases = FILLER_PHRASES[category][latency_type]
            if self._recent_indices[category][latency_type]:
                last_idx = self._recent_indices[category][latency_type][-1]
                return {"text": phrases[last_idx], "category": category, "latency": latency_type}
        except Exception:
            pass
        return {"category": category, "latency": latency_type}
