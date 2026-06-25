"""LLM-driven conversational agent service using LangGraph."""

import json
import logging
import os
import re
import time
from typing import Optional, Annotated, Sequence, TypedDict
import operator

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.groq_client import GroqClient
from app.models.response import ConversationResult
from app.models.session import SessionState
from app.services.order_service import OrderService
from app.services.verification_service import VerificationService
from app.session.manager import SessionManager
from datetime import datetime

logger = logging.getLogger(__name__)

SESSION_MAX_TURNS = int(os.getenv("SESSION_MAX_TURNS", "10"))

AGENT_SYSTEM_PROMPT = """You are a helpful, friendly customer support voice agent for an order management system.
Your ONLY purpose is to help callers check their order status, delivery dates, item summaries, and order numbers.
Keep your responses to 1-2 sentences since they will be spoken aloud over the phone.
Be warm, professional, and direct. Do not use markdown, emojis, or formatting.

CRITICAL OUTPUT RULE:
Your text response will be spoken aloud by a TTS engine. You must NEVER include raw JSON, function call syntax, tool names, parameter names, or any code in your spoken response. Your response must always be natural, conversational English. If you need to call a tool, use the tool_calls mechanism ONLY — never write tool calls in your text content.

VERIFICATION FLOW:
1. When a user wants to check their order, ask for their full name first, then their date of birth. Ask naturally, e.g. "Could you please tell me your full name?" and "And your date of birth?"
2. When you have both, call the verify_user tool. Convert any natural-language date (like "May 15th 1990") to YYYY-MM-DD internally. If the user provides an incomplete date (e.g., "May 19" without a year), explicitly ask them for the missing information before verifying.
3. If verification fails, naturally and dynamically explain that you couldn't find a matching account and ask them to try again. Vary your wording every time so you don't sound repetitive like a robot.
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

_TOOL_LEAK_PATTERNS = [
    re.compile(r'function\s*=\s*\w+\s*>\s*\{.*?\}', re.DOTALL),
    re.compile(r'<\|?tool_call\|?>.*?<\|?/tool_call\|?>', re.DOTALL),
    re.compile(r'\{\s*"name"\s*:\s*"\w+"\s*,\s*"arguments"\s*:', re.DOTALL),
    re.compile(r'\{\s*"function"\s*:', re.DOTALL),
    re.compile(r'</?function[^>]*>', re.IGNORECASE),
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

class AgentState(TypedDict):
    messages: Annotated[list[dict], operator.add]
    verified: bool
    user_name: Optional[str]
    dob: Optional[str]
    customer: Optional[dict]
    orders: list[dict]
    reply_text: str

class AgentService:
    """Primary orchestration layer for LLM-driven dialog using LangGraph."""

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
        self._memory = MemorySaver()
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        
        graph.add_node("agent", self._agent_node)
        graph.add_node("verify_tool", self._verify_tool_node)
        
        graph.add_edge(START, "agent")
        
        def route_agent(state: AgentState):
            last_msg = state["messages"][-1]
            if last_msg["role"] == "assistant" and "tool_calls" in last_msg and last_msg["tool_calls"]:
                return "verify_tool"
            return END
            
        graph.add_conditional_edges("agent", route_agent, {"verify_tool": "verify_tool", END: END})
        graph.add_edge("verify_tool", "agent")
        
        return graph.compile(checkpointer=self._memory)

    @staticmethod
    def _sanitize_reply_text(text: str) -> str:
        if not text:
            return text
        sanitized = text
        for pattern in _TOOL_LEAK_PATTERNS:
            sanitized = pattern.sub('', sanitized)
        sanitized = sanitized.strip()
        if not sanitized or len(sanitized) < 3:
            return "Let me look into that for you."
        return sanitized

    async def _agent_node(self, state: AgentState) -> dict:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dynamic_prompt = f"{AGENT_SYSTEM_PROMPT}\n\nCURRENT SYSTEM DATE AND TIME: {current_time}"
        messages_to_send = [{"role": "system", "content": dynamic_prompt}]

        if state.get("verified") and state.get("customer"):
            orders_context = ""
            if state.get("orders"):
                order_lines = []
                for o in state["orders"]:
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

            messages_to_send.append({
                "role": "system",
                "content": (
                    f"VERIFIED USER CONTEXT (internal — do NOT read this aloud or echo to the user):\n"
                    f"Customer name: {state.get('user_name', '')}\n"
                    f"The user is already verified. Do NOT ask for their name or date of birth again.\n"
                    f"Their orders:\n{orders_context}\n\n"
                    f"Use ONLY this order data to answer the user's questions. Do NOT make up information."
                )
            })

        # Append state messages (limiting to last N turns if necessary, but LangGraph keeps them)
        messages_to_send.extend(state["messages"][-20:])

        use_tools = not state.get("verified", False)
        llm_kwargs = dict(
            messages=messages_to_send,
            return_full_response=True,
            temperature=0.3,
            stage="graph_agent",
        )
        if use_tools:
            llm_kwargs["tools"] = AGENT_TOOLS
            llm_kwargs["tool_choice"] = "auto"

        response = await self._groq.chat_completion(**llm_kwargs)
        reply_message = response.choices[0].message
        
        assistant_msg = {"role": "assistant"}
        if reply_message.content:
            assistant_msg["content"] = reply_message.content
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
            assistant_msg["tool_calls"] = safe_tool_calls

        return {"messages": [assistant_msg], "reply_text": self._sanitize_reply_text(reply_message.content or "")}

    async def _verify_tool_node(self, state: AgentState) -> dict:
        last_msg = state["messages"][-1]
        updates = {"messages": []}
        
        for tc in last_msg.get("tool_calls", []):
            if tc["function"]["name"] == "verify_user":
                try:
                    args = json.loads(tc["function"]["arguments"])
                except Exception:
                    args = {}
                name = args.get("name", "")
                dob = args.get("dob", "")
                
                verification = await self._verification.verify(name, dob)
                if verification.verified and verification.customer:
                    updates["verified"] = True
                    updates["user_name"] = name
                    updates["dob"] = dob
                    updates["customer"] = verification.customer
                    orders = await self._orders.get_orders(verification.customer.get("id"))
                    updates["orders"] = orders
                    result_str = json.dumps({"verified": True, "message": "Account verified successfully.", "orders": orders})
                else:
                    result_str = json.dumps({"verified": False, "message": "No matching account found."})
                
                updates["messages"].append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str
                })
        return updates

    async def handle_user_text(self, session_id: str, user_text: str) -> ConversationResult:
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        # Get or create the session state (for compatibility with legacy SessionManager)
        session = await self._sessions.get_or_create(session_id)
        
        config = {"configurable": {"thread_id": session_id}}
        
        # Initialize graph state if empty
        graph_state = await self._graph.aget_state(config)
        if not graph_state.values:
            # Sync initial state from legacy SessionState if needed, but we start fresh
            await self._graph.aupdate_state(config, {
                "verified": session.verified,
                "user_name": session.user_name,
                "dob": session.dob,
                "customer": {"id": session.customer_id, "name": session.customer_name} if session.customer_id else None,
                "orders": session.orders if hasattr(session, "orders") else [],
                "messages": [],
            })
        
        user_msg = {"role": "user", "content": user_text}
        
        # Run graph
        async for output in self._graph.astream({"messages": [user_msg]}, config):
            pass  # It streams state updates, we just need the final state

        final_state = await self._graph.aget_state(config)
        state_values = final_state.values
        reply_text = state_values.get("reply_text", "")
        if not reply_text:
            reply_text = "I'm sorry, I couldn't process that. Let me know how I can help."
            
        # Update legacy SessionState for compatibility with the rest of the app logging
        session.verified = state_values.get("verified", False)
        session.user_name = state_values.get("user_name")
        session.dob = state_values.get("dob")
        if state_values.get("customer"):
            session.customer_id = state_values["customer"].get("id")
            session.customer_name = state_values["customer"].get("name")
            session.orders = state_values.get("orders", [])
        
        session.last_response = reply_text
        if user_text:
            session.add_turn("user", user_text, SESSION_MAX_TURNS)
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
            customer=state_values.get("customer"),
            orders=state_values.get("orders", []),
            timings=timings,
        )
