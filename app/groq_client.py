"""
Groq AI client — wraps STT, LLM chat completion, and TTS APIs.

Uses the official `groq` SDK (AsyncGroq) for STT and LLM,
and falls back to raw httpx for TTS (which may not yet be in the SDK).

All methods are async for maximum pipeline concurrency.
"""

import io
import logging
import os
from typing import AsyncGenerator, Optional, Any

import httpx
from groq import AsyncGroq
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()


class GroqClient:
    """
    Async client for AI APIs.
    
    Provides three core capabilities:
        1. speech_to_text  — Whisper-based transcription (Groq)
        2. chat_completion — LLM chat (Groq or OpenAI based on LLM_PROVIDER)
        3. text_to_speech  — Orpheus TTS (Groq)
    """

    # Default models — can be overridden per call
    STT_MODEL = os.getenv("STT_MODEL", "whisper-large-v3-turbo")
    
    if LLM_PROVIDER == "openai":
        LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    else:
        LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
        
    TTS_MODEL = os.getenv("TTS_MODEL", "canopylabs/orpheus-v1-english")
    TTS_VOICE = os.getenv("TTS_VOICE", "hannah")

    def __init__(self, api_key: Optional[str] = None, provider: Optional[str] = None):
        """
        Initialize the AI client.
        """
        self._groq_api_key = api_key or GROQ_API_KEY
        if not self._groq_api_key:
            logger.warning("GROQ_API_KEY is not set — Groq API calls (STT/TTS) will fail.")

        self.provider = provider or LLM_PROVIDER
        
        # Official SDK client for Groq (STT/TTS)
        self._client = AsyncGroq(api_key=self._groq_api_key)
        
        # LLM Client (OpenAI or Groq)
        if self.provider == "openai":
            if not OPENAI_API_KEY:
                logger.warning("OPENAI_API_KEY is not set — OpenAI API calls will fail.")
            self._llm_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        else:
            self._llm_client = self._client

        # Separate httpx client for TTS (raw REST) with keep-alive + pool tuning
        self._http = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={
                "Authorization": f"Bearer {self._groq_api_key}",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=120,
            ),
        )

    async def close(self):
        """Clean up HTTP sessions."""
        await self._client.close()
        await self._http.aclose()

    async def warmup(self):
        """
        Pre-establish TLS connections to Groq endpoints.

        Call once at startup so the first real request doesn't pay
        the handshake cost (~200-400ms).
        """
        try:
            # Lightweight request to establish the httpx connection
            await self._http.get("/models", timeout=5.0)
            logger.info("Groq connection warmed up (httpx pool)")
        except Exception as e:
            logger.warning(f"Warmup request failed (non-fatal): {e}")

    # -------------------------------------------------------------------------
    # 1. Speech-to-Text
    # -------------------------------------------------------------------------
    async def speech_to_text(
        self,
        audio_bytes: bytes,
        model: Optional[str] = None,
        language: str = "en",
        ext: str = "wav",
    ) -> str:
        """
        Transcribe audio using Groq's Whisper endpoint.

        Args:
            audio_bytes: WAV audio file bytes (16 kHz mono preferred).
            model: Whisper model name (default: whisper-large-v3-turbo).
            language: Language hint (default: "en").

        Returns:
            Transcribed text string.
        """
        model = model or self.STT_MODEL
        logger.info(f"STT: Sending {len(audio_bytes)} bytes to {model}")

        # The SDK expects a file-like object with a name attribute
        audio_file = (f"audio.{ext}", io.BytesIO(audio_bytes), f"audio/{ext}")

        transcription = await self._client.audio.transcriptions.create(
            file=audio_file,
            model=model,
            language=language,
            response_format="text",
        )

        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        logger.info(f"STT result: '{text}'")
        return text

    # -------------------------------------------------------------------------
    # 2. Chat Completion (LLM)
    # -------------------------------------------------------------------------
    async def chat_completion(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 256,
        stream: bool = False,
        return_full_response: bool = False,
        stage: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """
        Generate a chat response using Groq's LLM.

        Args:
            messages: List of message dicts [{"role": "system"|"user"|"assistant", "content": "..."}].
            model: LLM model name (default: llama-3.1-8b-instant).
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Maximum tokens in the response.
            stream: Whether to use streaming (collected into full text).
            return_full_response: Return the complete response object (useful for tool calls).
            **kwargs: Extra parameters like tools, tool_choice, etc.

        Returns:
            The assistant's reply as a string, or the full response object if return_full_response is True.
        """
        model = model or self.LLM_MODEL
        stage_info = f" [{stage}]" if stage else ""
        logger.info(f"LLM{stage_info}: Calling {model} with {len(messages)} messages")

        if stream:
            return await self._chat_completion_stream(messages, model, temperature, max_tokens)

        response = await self._llm_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        if return_full_response:
            return response
            
        reply = response.choices[0].message.content
        reply = reply.strip() if reply else ""
        logger.info(f"LLM result: '{reply[:100]}...'")
        return reply

    async def _chat_completion_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Stream chat completion and collect the full response."""
        chunks = []
        stream = await self._llm_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                chunks.append(delta.content)

        reply = "".join(chunks).strip()
        logger.info(f"LLM streamed result: '{reply[:100]}...'")
        return reply

    async def chat_completion_stream_tokens(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 150,
    ) -> AsyncGenerator[str, None]:
        """
        Yield individual LLM tokens as they arrive.

        This is the critical method for overlapping LLM and TTS:
        each yielded token can be buffered into sentences and sent
        to TTS immediately.

        Yields:
            Token strings, one at a time.
        """
        model = model or self.LLM_MODEL
        logger.info(f"LLM stream-tokens: {model}, {len(messages)} messages")

        stream = await self._llm_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    async def chat_completion_stream_with_tools(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 256,
        **kwargs,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """
        Stream chat completion yielding (type, data).
        type can be 'content' (yields strings) or 'tool_calls' (yields final tool calls list).
        """
        model = model or self.LLM_MODEL
        logger.info(f"LLM stream-with-tools: {model}, {len(messages)} messages")

        stream = await self._llm_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        )
        
        tool_calls = []
        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if not delta: continue
                
                if delta.content:
                    yield ("content", delta.content)
                    
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        while len(tool_calls) <= tc.index:
                            tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if tc.id:
                            tool_calls[tc.index]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_calls[tc.index]["function"]["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments

            if tool_calls:
                yield ("tool_calls", tool_calls)
        except Exception as e:
            if "Failed to call a function" in str(e):
                logger.warning("Groq API strict validation failed. Retrying without tools to allow text reply...")
                # Retry without tools
                fallback_stream = await self._llm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True
                )
                async for chunk in fallback_stream:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield ("content", delta.content)
            else:
                raise e

    # -------------------------------------------------------------------------
    # 3. Text-to-Speech
    # -------------------------------------------------------------------------
    async def text_to_speech(
        self,
        text: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> bytes:
        """
        Convert text to speech audio using Groq's TTS endpoint.

        Uses raw httpx request to the /audio/speech endpoint.

        Args:
            text: The text to synthesize.
            model: TTS model (default: playai-tts).
            voice: Voice name (default: Fritz-PlayAI).

        Returns:
            WAV audio bytes.
        """
        model = model or self.TTS_MODEL
        voice = voice or self.TTS_VOICE
        logger.info(f"TTS: Synthesizing {len(text)} chars with {model}/{voice}")

        # Use raw HTTP because the SDK may not yet support TTS
        response = await self._http.post(
            "/audio/speech",
            json={
                "model": model,
                "input": text,
                "voice": voice,
                "response_format": "wav",
            },
        )
        if response.status_code >= 400:
            logger.error(f"TTS API Error: {response.status_code} - {response.text}")
        response.raise_for_status()

        audio_bytes = response.content
        logger.info(f"TTS result: {len(audio_bytes)} bytes")
        return audio_bytes

    async def text_to_speech_streaming(
        self,
        text: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream TTS audio chunks as they arrive from Groq.

        Instead of waiting for the full audio response, yields
        chunks as the server sends them.  This reduces time-to-first-audio.

        Yields:
            Raw audio byte chunks (collectively form a valid WAV/PCM file).
        """
        model = model or self.TTS_MODEL
        voice = voice or self.TTS_VOICE
        logger.info(f"TTS stream: {len(text)} chars with {model}/{voice}")

        request = self._http.build_request(
            "POST",
            "/audio/speech",
            json={
                "model": model,
                "input": text,
                "voice": voice,
                "response_format": "wav",
            },
        )
        response = await self._http.send(request, stream=True)
        try:
            if response.status_code >= 400:
                body = await response.aread()
                logger.error(f"TTS stream API error: {response.status_code} - {body.decode()}")
                response.raise_for_status()
            async for chunk in response.aiter_bytes(chunk_size=4096):
                yield chunk
        finally:
            await response.aclose()
