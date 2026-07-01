"""
Deepgram real-time streaming STT client using raw websockets.
"""

import asyncio
import json
import logging
import os
from typing import AsyncGenerator

import websockets

logger = logging.getLogger(__name__)

class DeepgramStreamingClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # For 16kHz, 16-bit mono PCM (which is what VAD outputs)
        self.url = "wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1&model=nova-3&smart_format=true"
        self.ws = None
        self.running = False
        self.transcript_buffer = ""
        self.finalize_event = asyncio.Event()
        self.receive_task = None
        self.keepalive_task = None

    async def connect(self):
        headers = {
            "Authorization": f"Token {self.api_key}"
        }
        try:
            self.ws = await websockets.connect(self.url, additional_headers=headers)
            self.running = True
            self.receive_task = asyncio.create_task(self._receive_loop())
            self.keepalive_task = asyncio.create_task(self._keepalive_loop())
            logger.info("Persistent Deepgram WebSocket connected")
        except Exception as e:
            logger.error(f"Failed to connect to Deepgram: {e}")

    async def _keepalive_loop(self):
        while self.running:
            await asyncio.sleep(3)
            if self.ws and self.running:
                try:
                    await self.ws.send(json.dumps({"type": "KeepAlive"}))
                except Exception as e:
                    logger.debug(f"Deepgram KeepAlive failed: {e}")

    async def _receive_loop(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                if data.get("type") == "Results":
                    alternatives = data.get("channel", {}).get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        if transcript:
                            self.transcript_buffer += transcript + " "
                            
                    # Deepgram usually sends speech_final or is_final on flush
                    # Let's check for anything that looks like a flush or endpoint
                    if data.get("from_finalize") or data.get("speech_final") or data.get("is_final"):
                        self.finalize_event.set()
                        
                elif data.get("type") == "Metadata":
                    pass
        except websockets.exceptions.ConnectionClosed:
            logger.info("Deepgram WebSocket connection closed")
        except Exception as e:
            logger.error(f"Deepgram receive error: {e}")
        finally:
            self.running = False

    async def send_audio(self, chunk: bytes):
        if self.ws and self.running:
            try:
                await self.ws.send(chunk)
            except Exception as e:
                logger.error(f"Failed to send audio to Deepgram: {e}")

    async def get_transcript(self) -> str:
        if not self.ws or not self.running:
            return ""
            
        self.finalize_event.clear()
        try:
            # Force Deepgram to flush whatever audio it has
            await self.ws.send(json.dumps({"type": "Finalize"}))
        except Exception:
            pass
            
        # Wait up to 200ms for Deepgram to process and flush the buffer
        try:
            await asyncio.wait_for(self.finalize_event.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            pass
            
        t = self.transcript_buffer.strip()
        self.transcript_buffer = ""
        return t

    async def close(self):
        self.running = False
        if self.keepalive_task:
            self.keepalive_task.cancel()
        if self.ws:
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
                await self.ws.close()
            except Exception:
                pass
