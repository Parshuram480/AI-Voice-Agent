"""LLM-driven conversational agent service."""

import json
import logging
import os
import re
import re
import time
from typing import Optional

from app.groq_client import GroqClient
from app.models.response import ConversationResult
from app.models.session import SessionState
from app.services.order_service import OrderService
from app.services.verification_service import VerificationService
from app.session.manager import SessionManager

logger = logging.getLogger(__name__)

# --- Environment Variables ---
SESSION_MAX_TURNS = int(os.getenv("SESSION_MAX_TURNS", "10"))


AGENT_SYSTEM_PROMPT = """You are a helpful, friendly customer support voice agent for an order management system.
Your ONLY purpose is to help callers check their order status, delivery dates, item summaries, and order numbers.
Keep your responses to 1-2 sentences since they will be spoken aloud over the phone.
Be warm, professional, and direct. Do not use markdown, emojis, or formatting.

CRITICAL OUTPUT RULE:
Your text response will be spoken aloud by a TTS engine. You must NEVER include raw JSON, function call syntax, tool names, parameter names, or any code in your spoken response. Your response must always be natural, conversational English. If you need to call a tool, use the tool_calls mechanism ONLY — never write tool calls in your text content.

VERIFICATION FLOW:
1. When a user wants to check their order, ask for their full name first, then their date of birth. Ask naturally, e.g. "Could you please tell me your full name?" and "And your date of birth?"
2. When you have both, call the verify_user tool. Convert any natural-language date (like "May 15th 1990") to YYYY-MM-DD internally — NEVER tell the user what format you need.
3. If verification fails, say something like "I wasn't able to find an account with those details. Would you like to try again?" Do NOT reveal the format or technical reason.
4. After successful verification, immediately summarize their most recent order. Do NOT ask if they want you to proceed.

DO NOT (CRITICAL — violating these is a failure):
- NEVER tell the user what date format you need. Do NOT say "please provide your date of birth in YYYY-MM-DD format" or anything similar. Just ask for their date of birth naturally.
- NEVER echo the user's full name and date of birth back to them after verification. Simply say "I've verified your account" or "Great, I found your account" and move on.
- NEVER reveal internal system details like customer IDs, tool names, function names, or parameter formats.
- NEVER answer questions outside the scope of order status, delivery information, and item details. If the user asks about weather, news, general knowledge, or anything unrelated, politely say: "I'm only able to help with order-related questions. Is there anything about your orders I can help with?"
- NEVER make up order information. Only use the data provided to you in the system context. If information is not available, say so honestly.

CONVERSATION STYLE:
- Use the conversation history to understand context. If the user says "when will it arrive?" after discussing an order, you know which order they mean.
- Keep your tone natural, warm, and human. Avoid robotic phrasing.
- When answering follow-up questions, do not repeat the full order summary — just answer the specific question.
- If the user says goodbye or thanks, respond warmly and end the conversation.
"""

# Regex patterns to detect raw tool-call JSON leaked into reply text
_TOOL_LEAK_PATTERNS = [
    re.compile(r'function\s*=\s*\w+\s*>\s*\{.*?\}', re.DOTALL),   # function=verify_user>{...}
    re.compile(r'<\|?tool_call\|?>.*?<\|?/tool_call\|?>', re.DOTALL),  # <tool_call>...</tool_call>
    re.compile(r'\{\s*"name"\s*:\s*"\w+"\s*,\s*"arguments"\s*:', re.DOTALL),  # {"name":"verify_user","arguments":...}
    re.compile(r'\{\s*"function"\s*:', re.DOTALL),  # {"function":...}
    re.compile(r'</?function[^>]*>', re.IGNORECASE),  # <function> or </function>
]

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "verify_user",
            "description": "Verifies the user's account using their full name and date of birth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The user's full name (e.g., John Smith)."
                    },
                    "dob": {
                        "type": "string",
                        "description": "The user's date of birth, formatted as YYYY-MM-DD (e.g., 1990-05-15)."
                    }
                },
                "required": ["name", "dob"]
            }
        }
    }
]

class AgentService:
    """Primary orchestration layer for LLM-driven dialog."""

    def __init__(
        self,
        session_manager: SessionManager,
        groq_client: GroqClient,
        verification_service: VerificationService,
        order_service: OrderService,
    ) -> None:
        self._sessions = session_manager
        self._groq = groq_client
        self._verification = verification_service
        self._orders = order_service

    @staticmethod
    def _sanitize_reply_text(text: str) -> str:
        """Strip any raw tool-call JSON that leaked into the spoken reply."""
        if not text:
            return text
        sanitized = text
        for pattern in _TOOL_LEAK_PATTERNS:
            sanitized = pattern.sub('', sanitized)
        # Clean up leftover whitespace / punctuation fragments
        sanitized = sanitized.strip()
        if not sanitized or len(sanitized) < 3:
            # The entire reply was just leaked JSON — use a natural fallback
            return "Let me look into that for you."
        return sanitized

    async def handle_user_text(self, session_id: str, user_text: str) -> ConversationResult:
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        session = await self._sessions.get_or_create(session_id)
        
        # Append user turn to history
        if user_text:
            session.add_turn("user", user_text, SESSION_MAX_TURNS)
            
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dynamic_prompt = f"{AGENT_SYSTEM_PROMPT}\n\nCURRENT SYSTEM DATE AND TIME: {current_time}"
        messages = [{"role": "system", "content": dynamic_prompt}]
        
        # Inject system context if already verified — include cached order data
        # so the LLM can answer follow-up queries from memory (no repeated DB calls)
        if session.verified and session.customer_id:
            orders_context = ""
            if session.orders:
                order_lines = []
                for o in session.orders:
                    parts = [
                        f"Order #{o.get('order_number', 'N/A')}",
                        f"Status: {o.get('status', 'unknown')}",
                    ]
                    if o.get('estimated_arrival'):
                        parts.append(f"ETA: {o['estimated_arrival']}")
                    if o.get('items_summary'):
                        parts.append(f"Items: {o['items_summary']}")
                    order_lines.append(", ".join(parts))
                orders_context = "\n".join(order_lines)
            else:
                orders_context = "No orders found for this customer."

            messages.append({
                "role": "system",
                "content": (
                    f"VERIFIED USER CONTEXT (internal — do NOT read this aloud or echo to the user):\n"
                    f"Customer name: {session.customer_name or session.user_name}\n"
                    f"The user is already verified. Do NOT ask for their name or date of birth again.\n"
                    f"Their orders:\n{orders_context}\n\n"
                    f"Use ONLY this order data to answer the user's questions. Do NOT make up information."
                )
            })
            
        for turn in session.conversation_history:
            messages.append({"role": turn.role, "content": turn.text})

        # Only offer tools when the user is NOT yet verified
        # (once verified, all order data is in the system context — no tool needed)
        use_tools = not session.verified
        
        # LLM Call 1
        llm_kwargs = dict(
            messages=messages,
            return_full_response=True,
            temperature=0.3,
            stage="slot_extraction",
        )
        if use_tools:
            llm_kwargs["tools"] = AGENT_TOOLS
            llm_kwargs["tool_choice"] = "auto"
        
        response = await self._groq.chat_completion(**llm_kwargs)
        
        reply_message = response.choices[0].message
        
        customer: Optional[dict] = None
        orders: list[dict] = []
        
        # Handle tool calls
        if reply_message.tool_calls:
            safe_tool_calls = []
            for tc in reply_message.tool_calls:
                safe_tool_calls.append({
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                })
            
            safe_msg = {"role": "assistant"}
            if reply_message.content:
                safe_msg["content"] = reply_message.content
            safe_msg["tool_calls"] = safe_tool_calls
            messages.append(safe_msg)
            
            for tool_call in reply_message.tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                
                tool_result_str = "{}"
                if func_name == "verify_user":
                    name = args.get("name", "")
                    dob = args.get("dob", "")
                    verification = await self._verification.verify(name, dob)
                    if verification.verified:
                        session.verified = True
                        session.user_name = name
                        session.dob = dob
                        if verification.customer:
                            customer = verification.customer
                            session.customer_id = customer.get("id")
                            session.customer_name = customer.get("full_name") or customer.get("name")
                            
                            # Fetch orders ONCE and cache in session (in-memory)
                            orders_list = await self._orders.get_orders(session.customer_id)
                            orders = orders_list
                            session.orders = orders_list  # Cache for the session lifetime
                            if orders_list:
                                session.last_order = orders_list[0]
                                
                            tool_result_str = json.dumps({
                                "verified": True, 
                                "message": "Account verified successfully.",
                                "orders": orders_list
                            })
                    else:
                        tool_result_str = json.dumps({"verified": False, "message": "No matching account found."})
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result_str
                })
            
            # LLM Call 2 (after tool results)
            final_response = await self._groq.chat_completion(
                messages=messages,
                return_full_response=True,
                temperature=0.3,
                stage="response_generation"
            )
            reply_text = final_response.choices[0].message.content
        else:
            reply_text = reply_message.content

        reply_text = reply_text.strip() if reply_text else "I'm sorry, I couldn't process that. Let me know how I can help."
        reply_text = self._sanitize_reply_text(reply_text)
        
        session.last_response = reply_text
        session.add_turn("assistant", reply_text, SESSION_MAX_TURNS)
        await self._sessions.update(session)
        
        timings["total"] = round(time.perf_counter() - t0, 4)

        return ConversationResult(
            session_id=session.session_id,
            intent="llm_agent",
            reply_text=reply_text,
            state="AGENT_ACTIVE",
            should_end=False,
            verified=session.verified,
            customer=customer,
            orders=orders,
            timings=timings,
        )
