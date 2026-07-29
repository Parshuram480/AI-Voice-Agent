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
    },
    "universal": {
        "fast": [
            "Hmm.",
            "Mm-hmm.",
            "Okay.",
            "Ah."
        ],
        "medium": [],
        "slow": []
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
                        tasks.append((category, lat_type, phrase, filepath))
        
        if tasks:
            logger.info(f"Generating {len(tasks)} missing filler clips via Gemini Live WebSocket API...")
            
            # Process sequentially to respect strict free-tier rate limits (e.g. 10 requests)
            for category, lat_type, phrase, filepath in tasks:
                try:
                    await self._generate_and_cache(client, category, lat_type, phrase, filepath)
                    await asyncio.sleep(2) # Brief pause between sequential requests
                except Exception as e:
                    if "429" in str(e):
                        logger.error(f"Rate limit exceeded (429) while generating '{phrase}'. Stopping filler generation for this startup to allow the server to boot. Restart later to generate the rest.")
                        break # Stop generating the rest to avoid hanging the startup
                    else:
                        logger.error(f"Failed to generate filler clip for '{phrase}': {e}")
            
            logger.info(f"Finished generating clips.")
        else:
            logger.info("All filler clips loaded from disk cache.")
            
        self.is_ready = True

    async def _generate_and_cache(self, client, category: str, lat_type: str, phrase: str, filepath: Path):
        """Generates a single clip using Gemini Live API, with retries for errors."""
        model_name = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
        
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice_name)
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text="You are a text-to-speech engine. The user will provide a phrase. You must read it back EXACTLY as written, with no extra commentary, no introductions, and no acknowledgement. Just say the phrase.")]
            )
        )
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with client.aio.live.connect(model=model_name, config=config) as session:
                    await session.send(input=phrase, end_of_turn=True)
                    
                    audio_data = bytearray()
                    async for response in session.receive():
                        server_content = response.server_content
                        if server_content is not None:
                            model_turn = server_content.model_turn
                            if model_turn is not None:
                                for part in model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        audio_data.extend(part.inline_data.data)
                            
                            if server_content.turn_complete:
                                break
                                
                    if not audio_data:
                        raise ValueError("Received no audio data for phrase")
                        
                    from app.audio_utils import wav_bytes_to_pcm
                    try:
                        pcm_data, _, _, _ = wav_bytes_to_pcm(bytes(audio_data))
                    except Exception as e:
                        logger.warning(f"Failed to extract PCM from Live response (might already be raw PCM): {e}")
                        pcm_data = bytes(audio_data)
                        
                    # Save to disk as WAV (which wraps the raw PCM cleanly)
                    await asyncio.to_thread(self._save_wav, filepath, pcm_data)
                    
                    # Save raw PCM to memory
                    self._cache[category][lat_type].append(pcm_data)
                    return  # Success, exit the retry loop
                    
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                    sleep_time = 10
                    logger.warning(f"Rate limited (429) for phrase '{phrase}', retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(sleep_time)
                elif "500" in error_msg:
                    sleep_time = 5
                    logger.warning(f"Google API 500 error for '{phrase}', retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(sleep_time)
                else:
                    if attempt == max_retries - 1:
                        raise e
                    await asyncio.sleep(2)

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
        Returns None if no clips exist.
        """
        if not self.is_ready:
            return None
            
        if category not in self._cache or latency_type not in self._cache[category]:
            category = "thinking" # Fallback
            
        clips = self._cache.get(category, {}).get(latency_type, [])
        if not clips:
            if category == "universal":
                return None # Universal fillers should never fallback to non-neutral thinking phrases
                
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
