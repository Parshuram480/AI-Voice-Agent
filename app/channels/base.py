from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass

class ChannelAdapter(ABC):
    """
    Abstract base class for communication channel adapters.
    Unifies how outbound audio delivery and interruptions (barge-in) are handled.
    """

    @abstractmethod
    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Deliver TTS audio to the user."""
        pass

    @abstractmethod
    async def send_clear(self) -> None:
        """Flush the outbound audio buffer instantly (barge-in)."""
        pass

    async def send_audio_url(self, audio_url: str) -> bool:
        """Redirect call via REST API to play an audio file (if supported)."""
        return False

    @property
    @abstractmethod
    def channel_type(self) -> str:
        """Return the channel type identifier ('twilio', 'livekit', or 'none')."""
        pass


@dataclass
class CallContext:
    """
    Provider-agnostic context passed through the pipeline.
    """
    call_id: str
    session_id: str
    channel_adapter: Optional[ChannelAdapter] = None

    async def send_audio(self, pcm: bytes) -> None:
        if self.channel_adapter:
            await self.channel_adapter.send_audio(pcm)

    async def send_clear(self) -> None:
        if self.channel_adapter:
            await self.channel_adapter.send_clear()

    async def send_audio_url(self, audio_url: str) -> bool:
        if self.channel_adapter:
            return await self.channel_adapter.send_audio_url(audio_url)
        return False
