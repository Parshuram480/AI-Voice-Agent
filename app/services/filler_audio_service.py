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
DEFAULT_VOICE = "Puck"
# We match Gemini Live output format
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2

# Domain-agnostic filler phrases
FILLER_PHRASES = {
    "en": {
        "verification": {
            "medium": ["One second.", "Checking.", "Just a moment."],
            "slow": ["Let me verify those details for you.", "I'm pulling up your file now.", "One moment while I confirm that."],
            "fast": []
        },
        "lookup": {
            "medium": ["Checking.", "One moment.", "Looking now."],
            "slow": ["Let me see what I can find.", "I'm checking that for you now.", "Give me just a second to look that up."],
            "fast": []
        },
        "thinking": {
            "medium": ["Hmm.", "Let's see."],
            "slow": ["Let me think about that.", "Good question, let me check."],
            "fast": []
        },
        "universal": {
            "fast": ["Hmm.", "Mm-hmm.", "Okay.", "Ah.", "Right.", "I see.", "Got it.", "Yeah.", "Interesting.", "Sure.", "Oh."],
            "medium": [],
            "slow": []
        }
    },
    "hi_male": {
        "verification": {
            "medium": ["एक सेकंड।", "चेक कर लेता हूँ।", "बस एक सेकंड दीजिये।"],
            "slow": ["मैं एक सेकंड डिटेल्स चेक कर लेता हूँ।", "बस एक सेकंड दीजिये, मैं सिस्टम में देख रहा हूँ।", "एक मिनट, मैं कन्फर्म कर लेता हूँ।"],
            "fast": []
        },
        "lookup": {
            "medium": ["चेक कर रहा हूँ।", "एक मिनट।", "अभी देखता हूँ।"],
            "slow": ["बस एक सेकंड दीजिये, मैं देखता हूँ।", "मैं अभी आपके लिए सिस्टम में चेक कर रहा हूँ।", "मुझे एक सेकंड दीजिये।"],
            "fast": []
        },
        "thinking": {
            "medium": ["हम्म।", "एक मिनट..."],
            "slow": ["हम्म, मुझे सोचने दीजिये।", "अच्छा सवाल है, मैं चेक कर लेता हूँ।"],
            "fast": []
        },
        "universal": {
            "fast": ["हम्म।", "हाँ।", "ठीक है।", "अच्छा।"],
            "medium": [],
            "slow": []
        }
    },
    "hi_female": {
        "verification": {
            "medium": ["एक सेकंड।", "चेक कर लेती हूँ।", "बस एक सेकंड दीजिये।"],
            "slow": ["मैं एक सेकंड डिटेल्स चेक कर लेती हूँ।", "बस एक सेकंड दीजिये, मैं सिस्टम में देख रही हूँ।", "एक मिनट, मैं कन्फर्म कर लेती हूँ।"],
            "fast": []
        },
        "lookup": {
            "medium": ["चेक कर रही हूँ।", "एक मिनट।", "अभी देखती हूँ।"],
            "slow": ["बस एक सेकंड दीजिये, मैं देखती हूँ।", "मैं अभी आपके लिए सिस्टम में चेक कर रही हूँ।", "मुझे एक सेकंड दीजिये।"],
            "fast": []
        },
        "thinking": {
            "medium": ["हम्म।", "एक मिनट..."],
            "slow": ["हम्म, मुझे सोचने दीजिये।", "अच्छा सवाल है, मैं चेक कर लेती हूँ।"],
            "fast": []
        },
        "universal": {
            "fast": ["हम्म।", "हाँ।", "ठीक है।", "अच्छा।"],
            "medium": [],
            "slow": []
        }
    }
}

VOICE_GENDERS = {
    "Puck": "male",
    "Charon": "male",
    "Fenrir": "male",
    "Kore": "female",
    "Aoede": "female",
    "Achernar": "female"
}

class FillerAudioService:
    def __init__(self, cache_dir: str = "data/audio_cache/fillers", cooldown_size: int = 3, api_key: str = None):
        self.cache_dir = Path(cache_dir)
        self.cooldown_size = cooldown_size
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        
        # In-memory cache of PCM byte arrays
        # Format: self._cache[language][category][latency_type] = [pcm_bytes, pcm_bytes, ...]
        self._cache: dict[str, dict[str, dict[str, list[bytes]]]] = {}
        
        # Anti-repeat tracking
        # Format: self._recent_indices[language][category][latency_type] = deque()
        self._recent_indices: dict[str, dict[str, dict[str, deque[int]]]] = {}
        
        self.voice_name = os.getenv("GEMINI_VOICE", DEFAULT_VOICE)
        self.voice_gender = VOICE_GENDERS.get(self.voice_name, "male")
        self.voice_cache_dir = self.cache_dir / self.voice_name
        self.is_ready = False

    def _resolve_language(self, language: str) -> str:
        if language.lower().startswith("hi"):
            return f"hi_{self.voice_gender}"
        return language

    async def initialize(self, api_key: str = None):
        """
        Loads cached clips from disk or generates them if missing.
        Should be called at server startup.
        """
        if api_key:
            self.api_key = api_key
            
        self.voice_cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initializing FillerAudioService for voice '{self.voice_name}' (Gender: {self.voice_gender})...")
        
        # Build structure
        for lang in FILLER_PHRASES:
            self._cache[lang] = {}
            self._recent_indices[lang] = {}
            for cat in FILLER_PHRASES[lang]:
                self._cache[lang][cat] = {}
                self._recent_indices[lang][cat] = {}
                for lat in FILLER_PHRASES[lang][cat]:
                    self._cache[lang][cat][lat] = []
                    self._recent_indices[lang][cat][lat] = deque(maxlen=self.cooldown_size)
                
        # Generate or load
        tasks = []
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY not set. FillerAudioService disabled.")
            return

        client = genai.Client(api_key=self.api_key)

        for lang, categories in FILLER_PHRASES.items():
            # Skip genders that do not match the current voice
            if lang.startswith("hi_") and lang != f"hi_{self.voice_gender}":
                continue
                
            for category, latencies in categories.items():
                for lat_type, phrases in latencies.items():
                    if not phrases:
                        continue
                    
                    for i, phrase in enumerate(phrases):
                        filename = f"{lang}_{category}_{lat_type}_{i}.wav"
                        filepath = self.voice_cache_dir / filename
                        
                        if filepath.exists():
                            # Load from disk
                            pcm_data = self._load_wav(filepath)
                            self._cache[lang][category][lat_type].append(pcm_data)
                        else:
                            # Generate and save
                            tasks.append((lang, category, lat_type, phrase, filepath))
        
        if tasks:
            logger.info(f"Generating {len(tasks)} missing filler clips via Gemini Live WebSocket API...")
            
            # Process sequentially to respect strict free-tier rate limits (e.g. 10 requests)
            for i, (lang, category, lat_type, phrase, filepath) in enumerate(tasks, 1):
                try:
                    await self._generate_and_cache(client, lang, category, lat_type, phrase, filepath)
                    logger.info(f"Generated clip {i}/{len(tasks)}: '{phrase}'")
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

    async def _generate_and_cache(self, client, lang: str, category: str, lat_type: str, phrase: str, filepath: Path):
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
                parts=[types.Part(text=(
                    f"You are a warm, conversational, and highly natural AI assistant on a live phone call. "
                    f"You are speaking in language '{lang}'. "
                    f"The user just asked you a question, and you need to pause to check your system. "
                    f"You MUST speak the following phrase EXACTLY as written. "
                    f"STRICT RULE: Do NOT add any extra words, greetings, acknowledgements, or commentary. "
                    f"Crucially, deliver it in a natural, conversational, slightly distracted tone, as if you are typing on a keyboard or looking at a screen while saying it. "
                    f"Pace it naturally for a phone call. The phrase is: '{phrase}'"
                ))]
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
                    except Exception:
                        # Live API returns raw PCM directly, so wav_bytes_to_pcm will fail. This is expected.
                        pcm_data = bytes(audio_data)
                        
                    # Save to disk as WAV (which wraps the raw PCM cleanly)
                    await asyncio.to_thread(self._save_wav, filepath, pcm_data)
                    
                    # Save raw PCM to memory
                    self._cache[lang][category][lat_type].append(pcm_data)
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

    def select_filler(self, category: str, latency_type: str, language: str = "en") -> tuple[bytes, int] | None:
        """
        Returns a tuple of (pcm_bytes, sample_rate) for the requested category/latency.
        Returns None if no clips exist.
        """
        if not self.is_ready:
            return None
            
        language = self._resolve_language(language)
            
        if language not in self._cache:
            language = "en"
            
        lang_cache = self._cache.get(language, {})
            
        if category not in lang_cache or latency_type not in lang_cache[category]:
            category = "thinking" # Fallback
            
        clips = lang_cache.get(category, {}).get(latency_type, [])
        if not clips:
            if category == "universal":
                return None # Universal fillers should never fallback to non-neutral thinking phrases
                
            # Fallback to thinking/medium
            clips = lang_cache.get("thinking", {}).get("medium", [])
            category = "thinking"
            latency_type = "medium"
            if not clips:
                return None
                
        recent = self._recent_indices[language][category][latency_type]
        
        # Pick a non-recently-used clip
        available = [i for i in range(len(clips)) if i not in recent]
        if not available:
            available = list(range(len(clips))) # Reset if all on cooldown
            
        idx = random.choice(available)
        recent.append(idx)
        
        clip_data = clips[idx]
        return clip_data, SAMPLE_RATE

    def get_filler_metadata(self, category: str, latency_type: str, language: str = "en") -> dict:
        """Helper to get text context for logging (what did we likely play?)"""
        try:
            language = self._resolve_language(language)
            if language not in FILLER_PHRASES:
                language = "en"
            phrases = FILLER_PHRASES[language][category][latency_type]
            if self._recent_indices[language][category][latency_type]:
                last_idx = self._recent_indices[language][category][latency_type][-1]
                return {"text": phrases[last_idx], "category": category, "latency": latency_type, "language": language}
        except Exception:
            pass
        return {"category": category, "latency": latency_type, "language": language}
