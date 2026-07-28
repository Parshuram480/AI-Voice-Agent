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
from google.genai.types import AudioTranscriptionConfig

from app.services.verification_service import VerificationService
from app.services.order_service import OrderService
from app.utils.prompt_loader import get_prompts

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


# Global call-flow tool declarations shared across all modes
GLOBAL_TOOL_DECLARATIONS = [
    {
        "name": "end_call",
        "description": "Call this tool when the conversation is naturally finished — the user has received all the information they need and says goodbye, thanks you, or indicates they are done. This will gracefully end the phone call.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "out_of_scope",
        "description": "Call this tool when the user asks a question that is completely unrelated to the service domain (e.g. general knowledge, weather, jokes, math). Do NOT use this for questions that are even tangentially related to the business.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "reason": {"type": "STRING", "description": "Brief description of the off-topic question."}
            },
            "required": ["reason"]
        }
    }
]

# Prompt instructions injected into every system prompt for call flow control
CALL_FLOW_INSTRUCTIONS = """

--- CALL FLOW CONTROL ---
You have two special tools for managing the phone call lifecycle:

1. **end_call**: Use this IMMEDIATELY after you deliver your final goodbye message when the user indicates they are done (e.g. "thank you", "that's all", "bye", "nothing else"). Say goodbye FIRST, then call end_call.
2. **out_of_scope**: Use this when the user asks something completely unrelated to the service (e.g. "what is the capital of France?", "tell me a joke"). 
   - On the FIRST out-of-scope question: warn the user politely that you can only help with service-related queries.
   - On the SECOND out-of-scope question: inform the user the call is ending, then call end_call.

CRITICAL: When the user says goodbye or thanks you and has no more questions, you MUST call the end_call tool. Do not just say goodbye and wait.
"""


class GeminiLiveClient:
    """Manages a real-time, low-latency audio session with Gemini Live API."""

    def __init__(
        self,
        verification_service: VerificationService,
        order_service: OrderService,
        dynamic_tools: list = None,
        dynamic_executor = None,
        system_prompt: str = None
    ):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY is not set. Gemini Multimodal pipeline will fail.")
            
        self.client = genai.Client(api_key=self.api_key)
        self.model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
        self.voice = os.getenv("GEMINI_VOICE", "Puck")
        
        self.verification_service = verification_service
        self.order_service = order_service
        
        self.dynamic_tools = dynamic_tools
        self.dynamic_executor = dynamic_executor
        
        if system_prompt:
            self.system_prompt = system_prompt + CALL_FLOW_INSTRUCTIONS
        else:
            prompts = get_prompts()
            self.system_prompt = prompts.get("multimodal", {}).get("base_prompt", "You are a helpful assistant.") + CALL_FLOW_INSTRUCTIONS




    def _get_config(self) -> types.LiveConnectConfig:
        """Build the configuration for the live session."""
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription=AudioTranscriptionConfig(),
            output_audio_transcription=AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=self.system_prompt)]
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
            
            # Use dynamic tools if in dynamic mode, else fallback to hardcoded e-commerce tools
            base_tools = self.dynamic_tools if self.dynamic_tools is not None else [
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
            # Always append global call-flow tools
            tool_declarations = (base_tools or []) + GLOBAL_TOOL_DECLARATIONS
            
            # Recreate config with tools
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                input_audio_transcription=AudioTranscriptionConfig(),
                output_audio_transcription=AudioTranscriptionConfig(),
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                    )
                ),
                system_instruction=types.Content(
                    parts=[types.Part(text=self.system_prompt)]
                ),
                tools=[{"function_declarations": tool_declarations}] if tool_declarations else None
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
        
        # Handle global call-flow tools (end_call, out_of_scope) regardless of mode
        if name == "end_call":
            logger.info("[CALL FLOW] end_call tool triggered — marking session for termination")
            state["should_end"] = True
            return types.FunctionResponse(
                name=name,
                id=tool_call_id,
                response={"success": True, "message": "Call will be terminated after your goodbye message."}
            )
        
        if name == "out_of_scope":
            count = state.get("out_of_scope_count", 0) + 1
            state["out_of_scope_count"] = count
            reason = args.get("reason", "unknown")
            logger.info(f"[CALL FLOW] out_of_scope tool triggered (count={count}, reason={reason})")
            
            if count >= 2:
                state["should_end"] = True
                return types.FunctionResponse(
                    name=name,
                    id=tool_call_id,
                    response={
                        "warning_level": "terminate",
                        "out_of_scope_count": count,
                        "message": "This is the second out-of-scope question. The call must now be terminated. Say goodbye and then call end_call."
                    }
                )
            else:
                return types.FunctionResponse(
                    name=name,
                    id=tool_call_id,
                    response={
                        "warning_level": "warning",
                        "out_of_scope_count": count,
                        "message": "This is the first out-of-scope question. Warn the user: 'I can only help you with questions related to our service. Please ask about that, or I will have to end the call.'"
                    }
                )
        
        # Delegate to Dynamic Executor if in dynamic mode
        if self.dynamic_executor is not None:
            return await self.dynamic_executor.execute(tool_call_id, name, args, state)
            
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
