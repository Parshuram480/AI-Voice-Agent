import os
import logging
from typing import AsyncGenerator, Optional
from cartesia import AsyncCartesia

logger = logging.getLogger(__name__)

class CartesiaClient:
    def __init__(self):
        api_key = os.getenv("CARTESIA_API_KEY")
        if not api_key:
            logger.warning("CARTESIA_API_KEY is not set. Cartesia TTS will fail if invoked.")
        self.client = AsyncCartesia(api_key=api_key)
        # High quality conversational voice (e.g. British or standard conversational)
        self.default_voice = os.getenv("CARTESIA_VOICE_ID", "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc") 

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> bytes:
        """
        Convert text to speech audio using Cartesia's TTS endpoint.
        Returns WAV audio bytes.
        """
        voice = voice_id or self.default_voice
        logger.info(f"Cartesia TTS: Synthesizing {len(text)} chars with {voice}")
        
        audio_chunks = []
        audio_stream = await self.client.tts.sse(
            model_id="sonic-3.5",
            transcript=text,
            voice={"mode": "id", "id": voice},
            output_format={
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 24000,
            },
        )
        
        async for chunk in audio_stream:
            if hasattr(chunk, "audio") and chunk.audio:
                audio_chunks.append(chunk.audio)
                
        audio_bytes = b"".join(audio_chunks)
        from app.audio_utils import build_wav
        wav_bytes = build_wav(audio_bytes, sample_rate=24000)
        logger.info(f"Cartesia TTS result: {len(wav_bytes)} bytes (WAV)")
        return wav_bytes

    async def text_to_speech_streaming(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream TTS audio chunks as they arrive from Cartesia.
        """
        voice = voice_id or self.default_voice
        logger.info(f"Cartesia TTS stream: {len(text)} chars with {voice}")
        
        audio_stream = await self.client.tts.sse(
            model_id="sonic-3.5",
            transcript=text,
            voice={"mode": "id", "id": voice},
            output_format={
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 24000,
            },
        )
        
        async for chunk in audio_stream:
            if hasattr(chunk, "audio") and chunk.audio:
                yield chunk.audio
