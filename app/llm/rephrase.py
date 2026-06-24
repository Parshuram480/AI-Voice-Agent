"""Controlled LLM rephrasing for deterministic responses."""
from __future__ import annotations

import os

# --- Environment Variables ---
LLM_REPHRASE = os.getenv("LLM_REPHRASE", "false").lower() in ("1", "true", "yes", "on")
LLM_REPHRASE_MAX_TOKENS = int(os.getenv("LLM_REPHRASE_MAX_TOKENS", "96"))
LLM_REPHRASE_TEMPERATURE = float(os.getenv("LLM_REPHRASE_TEMPERATURE", "0.2"))

from typing import AsyncGenerator

from app.groq_client import GroqClient


class LLMRephraser:
    """Rephrase deterministic responses without altering facts."""

    SYSTEM_PROMPT = (
        "You are a customer support assistant. "
        "Rephrase the provided response to sound natural, short, and clear. "
        "Do not add or remove facts. "
        "If the response asks for clarification, keep it as a question. "
        "Return only the final response text." 
    )

    def __init__(self, groq_client: GroqClient) -> None:
        self._groq = groq_client

    @property
    def enabled(self) -> bool:
        return LLM_REPHRASE

    async def rephrase_text(self, draft_text: str) -> str:
        if not draft_text or not self.enabled:
            return draft_text

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": draft_text},
        ]

        try:
            return await self._groq.chat_completion(
                messages,
                temperature=LLM_REPHRASE_TEMPERATURE,
                max_tokens=LLM_REPHRASE_MAX_TOKENS,
                stream=False,
            )
        except Exception:
            return draft_text

    async def stream_rephrase(self, draft_text: str) -> AsyncGenerator[str, None]:
        if not draft_text or not self.enabled:
            yield draft_text
            return

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": draft_text},
        ]

        async for token in self._groq.chat_completion_stream_tokens(
            messages,
            temperature=LLM_REPHRASE_TEMPERATURE,
            max_tokens=LLM_REPHRASE_MAX_TOKENS,
        ):
            yield token
