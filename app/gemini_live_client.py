"""Client for interacting with the Gemini Multimodal Live API via WebSockets."""

import asyncio
import json
import logging
import os
import base64
from typing import AsyncGenerator, Callable, Optional, Dict, Any

try:
    from langsmith import traceable
except ImportError:
    # Fallback if langsmith is not installed or enabled
    def traceable(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper

from google import genai
from google.genai import types

from app.services.verification_service import VerificationService
from app.services.order_service import OrderService
from app.services.agent_service import AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Monkey-patch websockets.asyncio.client.connect to disable ping_interval/timeout
# Gemini Live API backend often doesn't respond to websocket pings causing 1011 drop after 40s.
import websockets.asyncio.client
_original_ws_connect = websockets.asyncio.client.connect

def _patched_ws_connect(*args, **kwargs):
    kwargs["ping_interval"] = None
    kwargs["ping_timeout"] = None
    return _original_ws_connect(*args, **kwargs)

websockets.asyncio.client.connect = _patched_ws_connect


class GeminiLiveClient:
    """Manages a real-time, low-latency audio session with Gemini Live API."""

    def __init__(
        self,
        verification_service: VerificationService,
        order_service: OrderService,
    ):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY is not set. Gemini Multimodal pipeline will fail.")
            
        self.client = genai.Client(api_key=self.api_key)
        self.model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
        self.voice = os.getenv("GEMINI_VOICE", "Puck")
        
        self.verification_service = verification_service
        self.order_service = order_service
        

    def _get_config(self) -> types.LiveConnectConfig:
        """Build the configuration for the live session."""
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=AGENT_SYSTEM_PROMPT)]
            )
        )

    def connect(self):
        """Connect to the Gemini Live WebSocket.
        Returns the async context manager from the SDK.
        """
        logger.info(f"Connecting to Gemini Live API ({self.model}) with voice {self.voice}...")
        try:
            # We must use 'async with' when calling this, so we return the context manager
            config = self._get_config()
            # Hack: Manually inject tool definitions because google-genai's LiveConnectConfig 
            # might not have a simple 'tools' parameter mapping in all versions.
            # Actually, types.LiveConnectConfig supports 'tools'. Let's add it properly.
            
            tool_declarations = [
                {
                    "name": "verify_user",
                    "description": "Verifies account AND fetches their orders automatically. REQUIRES BOTH full name and DOB. NEVER call if DOB is missing.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING", "description": "User's full name."},
                            "dob": {"type": "STRING", "description": "YYYY-MM-DD. Ask for missing info (e.g. year) if incomplete."}
                        },
                        "required": ["name", "dob"]
                    }
                },
                {
                    "name": "get_order_status",
                    "description": "Fetches latest orders for verified user.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING", "description": "Optional. Automatically ignored by backend."},
                            "dob": {"type": "STRING", "description": "Optional. Automatically ignored by backend."}
                        }
                    }
                }
            ]
            
            # Recreate config with tools
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                    )
                ),
                system_instruction=types.Content(
                    parts=[types.Part(text=AGENT_SYSTEM_PROMPT)]
                ),
                tools=[{"function_declarations": tool_declarations}]
            )
            
            return self.client.aio.live.connect(
                model=self.model,
                config=config
            )
        except Exception as e:
            logger.error(f"Failed to connect to Gemini Live: {e}")
            raise e

    @traceable(name="gemini_live_execute_tool_call")
    async def execute_tool_call(
        self,
        tool_call_id: str,
        name: str,
        args: dict,
        state: dict,
    ) -> types.FunctionResponse:
        """
        Execute the requested tool and return a FunctionResponse ready to send to Gemini.
        `state` is a dictionary holding the current conversation state (verified status, customer data, orders).
        """
        logger.info(f"Executing tool call: {name} with args {args}")
        
        try:
            if name == "verify_user":
                user_name = args.get("name", "")
                dob = args.get("dob", "")
                
                # Perform verification using the existing service
                result = await self.verification_service.verify(user_name, dob)
                
                # Update state
                state["verified"] = result.verified
                state["user_name"] = user_name
                state["dob"] = dob
                
                if result.verified:
                    state["customer"] = result.customer
                    # Automatically fetch orders when verified, matching existing behavior
                    orders = await self.order_service.get_orders(result.customer["id"])
                    state["orders"] = orders
                    
                    return types.FunctionResponse(
                        name=name,
                        id=tool_call_id,
                        response={
                            "verified": True,
                            "name_used": user_name,
                            "dob_used": dob,
                            "message": f"Successfully verified. Found {len(orders)} orders.",
                            "orders": orders
                        }
                    )
                else:
                    return types.FunctionResponse(
                        name=name,
                        id=tool_call_id,
                        response={
                            "verified": False,
                            "name_used": user_name,
                            "dob_used": dob,
                            "message": "Verification failed. Name or DOB did not match.",
                        }
                    )
                    
            elif name == "get_order_status":
                if not state.get("verified") or not state.get("customer"):
                    return types.FunctionResponse(
                        name=name,
                        id=tool_call_id,
                        response={"error": "User not verified. Please call verify_user first."}
                    )
                
                orders = await self.order_service.get_orders(state["customer"]["id"])
                state["orders"] = orders
                
                return types.FunctionResponse(
                    name=name,
                    id=tool_call_id,
                    response={
                        "orders": orders
                    }
                )
            
            else:
                return types.FunctionResponse(
                    name=name,
                    id=tool_call_id,
                    response={"error": f"Unknown function {name}"}
                )
                
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return types.FunctionResponse(
                name=name,
                id=tool_call_id,
                response={"error": str(e)}
            )
