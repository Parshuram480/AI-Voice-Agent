"""
app/retell_handler.py — Retell AI Custom LLM WebSocket and API Handler.

Handles:
1. Retell Custom LLM WebSocket protocol (/retell-llm-websocket/{call_id})
   - Turn-taking, heartbeats (ping_pong), and barge-in / interruption cancellation.
   - Live token streaming back to Retell using Groq / LLM client.
2. Outbound phone calls and web calls via official retell-sdk.
"""

import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any, List
from fastapi import WebSocket, WebSocketDisconnect
from retell import Retell

logger = logging.getLogger(__name__)

RETELL_API_KEY = os.getenv("RETELL_API_KEY", "")
RETELL_AGENT_ID = os.getenv("RETELL_AGENT_ID", "")
RETELL_PHONE_NUMBER = os.getenv("RETELL_PHONE_NUMBER", "")


class RetellCustomLLMHandler:
    """
    Manages communication between Retell AI and the custom backend LLM.
    """

    def __init__(self, llm_client=None, default_system_prompt: Optional[str] = None):
        self.llm_client = llm_client
        self.api_key = RETELL_API_KEY
        self.agent_id = RETELL_AGENT_ID
        self.client: Optional[Retell] = None

        if self.api_key:
            try:
                self.client = Retell(api_key=self.api_key)
                logger.info("✓ Retell SDK client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Retell SDK client: {e}")
        else:
            logger.warning("RETELL_API_KEY not found in environment — outbound calls via Retell will fail.")

        self.default_system_prompt = default_system_prompt or (
            "You are a helpful, professional, and conversational AI phone agent. "
            "Respond naturally, concisely, and keep your answers within 1 to 2 sentences when possible."
        )

    # -------------------------------------------------------------------------
    # WebSocket Protocol Handling
    # -------------------------------------------------------------------------
    async def handle_websocket(self, websocket: WebSocket, call_id: str, client_id: Optional[int] = None):
        """
        Main WebSocket loop for a Retell call session.
        """
        await websocket.accept()
        logger.info(f"[Retell LLM] Connected for call_id: {call_id} (client_id: {client_id})")

        # 1. Send initial configuration to Retell
        config_payload = {
            "response_type": "config",
            "config": {
                "auto_reconnect": True,
                "call_details": True,
            }
        }
        await websocket.send_text(json.dumps(config_payload))

        active_stream_task: Optional[asyncio.Task] = None
        call_details: Dict[str, Any] = {}

        try:
            while True:
                data_text = await websocket.receive_text()
                if not data_text:
                    continue

                event = json.loads(data_text)
                interaction_type = event.get("interaction_type")

                # Handle Ping/Pong keep-alive
                if interaction_type == "ping_pong":
                    timestamp = event.get("timestamp")
                    await websocket.send_text(json.dumps({
                        "response_type": "ping_pong",
                        "timestamp": timestamp
                    }))
                    continue

                # Handle Call Details metadata from Retell
                if interaction_type == "call_details":
                    call_details = event.get("call", {})
                    logger.info(f"[Retell LLM] Call details received for {call_id} (Caller: {call_details.get('from_number', 'WebCall')})")
                    continue

                # Handle live transcription updates while user is speaking (speech preview)
                if interaction_type == "update_only":
                    transcript = event.get("transcript", [])
                    last_speech = next((t.get("content") for t in reversed(transcript) if t.get("role") == "user"), "")
                    if last_speech:
                        logger.info(f"[Retell LLM] Caller speaking (live): '{last_speech}'")
                    continue

                # Handle agent response triggers (response_required or reminder_required)
                if interaction_type in ("response_required", "reminder_required"):
                    response_id = event.get("response_id")
                    transcript_history = event.get("transcript", [])

                    # If caller spoke again while previous response was generating (barge-in), cancel the old task
                    if active_stream_task and not active_stream_task.done():
                        logger.info(f"[Retell LLM] Interruption detected! Cancelling previous stream for call {call_id}")
                        active_stream_task.cancel()

                    # Start streaming new response
                    active_stream_task = asyncio.create_task(
                        self._stream_llm_response(
                            websocket=websocket,
                            call_id=call_id,
                            response_id=response_id,
                            transcript_history=transcript_history,
                            call_details=call_details,
                            client_id=client_id
                        )
                    )

        except WebSocketDisconnect:
            logger.info(f"[Retell LLM] WebSocket disconnected for call_id: {call_id}")
        except Exception as e:
            logger.error(f"[Retell LLM] Exception in WebSocket loop for {call_id}: {e}", exc_info=True)
        finally:
            if active_stream_task and not active_stream_task.done():
                active_stream_task.cancel()

    async def _stream_llm_response(
        self,
        websocket: WebSocket,
        call_id: str,
        response_id: int,
        transcript_history: List[Dict[str, str]],
        call_details: Dict[str, Any],
        client_id: Optional[int]
    ):
        """
        Generate and stream LLM response tokens back to Retell over WebSocket.
        """
        try:
            # Build and sanitize messages list for the LLM
            messages = [{"role": "system", "content": self.default_system_prompt}]

            for turn in transcript_history:
                role = turn.get("role")
                content = turn.get("content", "").strip()
                if not content:
                    continue
                # Map Retell roles to OpenAI / Groq / Gemini roles ('agent' -> 'assistant')
                llm_role = "assistant" if role == "agent" else "user"

                # Merge consecutive turns with same role to ensure strict alternating turns
                if len(messages) > 1 and messages[-1]["role"] == llm_role:
                    messages[-1]["content"] += f" {content}"
                else:
                    messages.append({"role": llm_role, "content": content})

            # Gemini requirement: Requests must always end with a user turn
            while len(messages) > 1 and messages[-1]["role"] == "assistant":
                messages.pop()

            # Ensure at least one user message exists
            if len(messages) == 1:
                messages.append({"role": "user", "content": "Hello"})

            last_user_msg = messages[-1]["content"]
            logger.info(f"[Retell LLM] Generating reply for [response_id={response_id}]: '{last_user_msg[:80]}'")

            # Stream tokens using Groq / configured LLM client
            if self.llm_client and hasattr(self.llm_client, "chat_completion_stream_tokens"):
                async for token in self.llm_client.chat_completion_stream_tokens(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=150
                ):
                    await websocket.send_text(json.dumps({
                        "response_type": "response",
                        "response_id": response_id,
                        "content": token,
                        "content_complete": False
                    }))
            else:
                # Fallback if no streaming LLM client is bound
                fallback_msg = "Hello! I am connected to your custom backend."
                await websocket.send_text(json.dumps({
                    "response_type": "response",
                    "response_id": response_id,
                    "content": fallback_msg,
                    "content_complete": False
                }))

            # Send completion signal for this turn
            await websocket.send_text(json.dumps({
                "response_type": "response",
                "response_id": response_id,
                "content": "",
                "content_complete": True
            }))
            logger.info(f"[Retell LLM] Completed streaming response for [response_id={response_id}]")

        except asyncio.CancelledError:
            logger.info(f"[Retell LLM] Stream cancelled for response_id={response_id}")
            raise
        except Exception as e:
            logger.error(f"[Retell LLM] Error streaming LLM response: {e}", exc_info=True)
            # Try to send final complete packet so Retell doesn't hang
            try:
                await websocket.send_text(json.dumps({
                    "response_type": "response",
                    "response_id": response_id,
                    "content": "I apologize, but I encountered an issue generating a response.",
                    "content_complete": True
                }))
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # REST API Call Initiation Helpers
    # -------------------------------------------------------------------------
    def create_phone_call(
        self,
        to_number: str,
        from_number: Optional[str] = None,
        agent_id: Optional[str] = None,
        dynamic_variables: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Initiate an outbound phone call via Retell SDK.
        """
        if not self.client:
            raise RuntimeError("Retell client is not initialized. Please verify RETELL_API_KEY.")

        from_num = from_number or RETELL_PHONE_NUMBER or os.getenv("TWILIO_PHONE_NUMBER")
        target_agent = agent_id or self.agent_id

        if not from_num:
            raise ValueError("No from_number provided and RETELL_PHONE_NUMBER / TWILIO_PHONE_NUMBER is not set.")

        logger.info(f"[Retell SDK] Creating phone call: {from_num} -> {to_number} using agent {target_agent}")
        return self.client.call.create_phone_call(
            from_number=from_num,
            to_number=to_number,
            override_agent_id=target_agent,
            retell_llm_dynamic_variables=dynamic_variables or {}
        )

    def create_web_call(
        self,
        agent_id: Optional[str] = None,
        dynamic_variables: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Create a web call token for browser-based testing.
        """
        if not self.client:
            raise RuntimeError("Retell client is not initialized. Please verify RETELL_API_KEY.")

        target_agent = agent_id or self.agent_id
        logger.info(f"[Retell SDK] Creating web call for agent {target_agent}")
        return self.client.call.create_web_call(
            agent_id=target_agent,
            retell_llm_dynamic_variables=dynamic_variables or {}
        )
