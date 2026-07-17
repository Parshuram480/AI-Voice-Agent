"""LLM-driven conversational agent service using LangGraph."""

import json
import logging
import os
import re
import time
from typing import Optional, Annotated, Sequence, TypedDict, Callable
import operator

import asyncio
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.groq_client import GroqClient
from app.models.response import ConversationResult
from app.models.session import SessionState
from app.services.order_service import OrderService
from app.services.verification_service import VerificationService
from app.session.manager import SessionManager
from app.logging.logger import log_llm_metrics
from datetime import datetime, date
from app.system_database import SystemDatabase
from app.utils.prompt_loader import get_prompts
from app.dynamic_db_client import DynamicDbClient

logger = logging.getLogger(__name__)

SESSION_MAX_TURNS = int(os.getenv("SESSION_MAX_TURNS", "10"))


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
            "description": "Verifies account AND fetches their orders automatically. REQUIRES BOTH full name and DOB. NEVER call this tool until the user has explicitly answered 'Yes' to confirm their Name and DOB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "User's full name."},
                    "dob": {"type": "string", "description": "YYYY-MM-DD. Ask for missing info (e.g. year) if incomplete."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Fetches latest orders for verified user. CRITICAL: NEVER call this tool if the user is not verified yet.",
            "parameters": {
                "type": "object", 
                "properties": {
                    "name": {"type": "string", "description": "Optional. Automatically ignored by backend."},
                    "dob": {"type": "string", "description": "Optional. Automatically ignored by backend."}
                }
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
    summary: Optional[str]
    turn_metrics: dict
    memory_tokens_input: Annotated[int, operator.add]
    memory_tokens_output: Annotated[int, operator.add]

class AgentService:
    """Primary orchestration layer for LLM-driven dialog using LangGraph."""

    def __init__(
        self,
        session_manager: SessionManager,
        groq_client_1: GroqClient,
        groq_client_2: GroqClient,
        verification_service: VerificationService,
        order_service: OrderService,
    ) -> None:
        self._sessions = session_manager
        self._groq_1 = groq_client_1
        self._groq_2 = groq_client_2
        self._verification = verification_service
        self._orders = order_service
        self._system_db = SystemDatabase()
        self._memory = MemorySaver()
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        
        graph.add_node("llm1", self._llm1_node)
        graph.add_node("verify_tool", self._verify_tool_node)
        graph.add_node("llm2", self._llm2_node)
        
        graph.add_edge(START, "llm1")
        
        def route_llm1(state: AgentState):
            last_msg = state["messages"][-1]
            if last_msg["role"] == "assistant" and "tool_calls" in last_msg and last_msg["tool_calls"]:
                return "verify_tool"
            return END
            
        graph.add_conditional_edges("llm1", route_llm1, {"verify_tool": "verify_tool", END: END})
        graph.add_edge("verify_tool", "llm2")
        graph.add_edge("llm2", END)
        
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

    async def _llm1_node(self, state: AgentState, config: RunnableConfig) -> dict:
        turn_metrics = state.get("turn_metrics", {})
        if "timing_prompt_assembly_start" not in turn_metrics:
            turn_metrics["timing_prompt_assembly_start"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
        session_id = config.get("configurable", {}).get("thread_id", "unknown")
        session = await self._sessions.get_or_create(session_id)
        client_id = getattr(session, "client_id", None)
        
        mapping = None
        if client_id is not None:
            try:
                mapping = await self._system_db.get_client_domain_mapping(client_id)
            except Exception as e:
                logger.error(f"Error fetching mapping for client {client_id}: {e}")

        logger.info(f"[_LLM1_NODE] Resolved session_id/thread_id: {session_id}, client_id: {client_id}")
        if mapping:
            logger.info(f"[_LLM1_NODE] Loaded domain mapping: {mapping.get('domain_name')}")
            base_prompt = mapping["system_prompt_llm1"]
            tools_to_use = json.loads(mapping["tools_schema"])
        else:
            logger.info(f"[_LLM1_NODE] No domain mapping found, defaulting to Order Tracking.")
            base_prompt = get_prompts().get("cascade", {}).get("llm1_base", "You are a helpful assistant.")
            tools_to_use = AGENT_TOOLS

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dynamic_prompt = f"{base_prompt}\n\nCURRENT SYSTEM DATE AND TIME: {current_time}"
        messages_to_send = [{"role": "system", "content": dynamic_prompt}]

        if state.get("verified") and state.get("customer"):
            messages_to_send.append({
                "role": "system",
                "content": (
                    f"CRITICAL STATE: You are ALREADY VERIFIED as {state['customer'].get('full_name', 'Unknown')}.\n"
                    f"DO NOT ask for name or DOB. Use the `get_order_status` tool to answer their queries immediately.\n"
                    f"IMPORTANT: If the user asks for specific order details (like order number or tracking) and you don't have them in your immediate context, you MUST call the `get_order_status` tool again to retrieve them. NEVER say you don't have the information or ask the user for their order number."
                )
            })

        if state.get("summary"):
            messages_to_send.append({
                "role": "system",
                "content": f"Here is a brief summary of the conversation so far: {state['summary']}"
            })
            messages_to_send.extend(state["messages"][-8:])
        else:
            messages_to_send.extend(state["messages"][-8:])

        use_tools = True
        llm_kwargs = dict(
            messages=messages_to_send,
            temperature=0.3,
        )
        if use_tools:
            llm_kwargs["tools"] = tools_to_use
            llm_kwargs["tool_choice"] = "auto"

        turn_metrics["timing_serialization_start"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        on_llm_token = config.get("configurable", {}).get("on_llm_token")
        
        reply_content = ""
        tool_calls = []
        
        start_time = time.perf_counter()
        first_token_time = None
        
        if "timing_prompt_assembly_end" not in turn_metrics:
            turn_metrics["timing_prompt_assembly_end"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        else:
            turn_metrics["timing_second_llm_send"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
        # --- LLM Metrics Tracking Variables ---
        llm_usage = None
        streaming_started_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        history_tokens = 0
        summary_tokens = 0
        current_user_tokens = 0
        
        # Estimate token lengths (roughly 4 chars = 1 token for basic counting)
        for msg in messages_to_send:
            content_len = len(str(msg.get("content", ""))) // 4
            if msg.get("role") == "system":
                summary_tokens += content_len
            elif msg == messages_to_send[-1] and msg.get("role") == "user":
                current_user_tokens += content_len
            else:
                history_tokens += content_len
        
        turn_metrics["timing_serialization_end"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        # ----------------------------------------
        
        # --- Industry Standard Stream Interceptor ---
        # We buffer the first few characters to detect if the LLM is leaking a tool call
        # as raw text. If it is, we mute the stream to TTS to prevent hallucinated code from being spoken.
        stream_open = False
        mute_stream = False
        held_text = ""
        
        async for chunk_type, chunk_data in self._groq_1.chat_completion_stream_with_tools(**llm_kwargs):
            if chunk_type == "timing":
                if chunk_data["event"] not in turn_metrics:
                    turn_metrics[chunk_data["event"]] = chunk_data["time"]
                continue
                
            if chunk_type == "usage":
                llm_usage = chunk_data
                continue
                
            if not first_token_time:
                first_token_time = time.perf_counter()
                logger.info(f"LLM TTFT internally measured: {round(first_token_time - start_time, 4)}s")
                tok_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                if "timing_first_token" not in turn_metrics:
                    turn_metrics["timing_first_token"] = tok_time
                else:
                    turn_metrics["timing_second_first_token"] = tok_time
            
            if chunk_type == "content":
                reply_content += chunk_data
                
                if mute_stream:
                    continue
                    
                if not stream_open:
                    held_text += chunk_data
                    # Check for leaked tool call signatures in the first few characters
                    text_lower = held_text.lower().strip()
                    
                    # If it definitely starts like a tool call, mute the stream permanently
                    if text_lower.startswith("function=") or text_lower.startswith("<function") or text_lower.startswith("<tool") or text_lower.startswith('{"name":') or text_lower.startswith('{"function"'):
                        mute_stream = True
                        continue
                        
                    # If it starts with an ambiguous character ('f', '<', '{'), buffer up to 15 chars to be sure
                    if text_lower.startswith("f") or text_lower.startswith("<") or text_lower.startswith("{"):
                        if len(text_lower) < 15:
                            continue  # Keep buffering
                            
                    # If we reach here, it's either not starting with a suspicious prefix, 
                    # or it broke the pattern (e.g. "for your order..."). Flush the buffer and open the stream.
                    stream_open = True
                    if on_llm_token and held_text:
                        try:
                            on_llm_token(held_text)
                        except Exception as e:
                            logger.debug(f"on_llm_token failed: {e}")
                    held_text = ""
                else:
                    if on_llm_token:
                        try:
                            on_llm_token(chunk_data)
                        except Exception as e:
                            logger.debug(f"on_llm_token failed: {e}")
            elif chunk_type == "tool_calls":
                tool_calls = chunk_data

        streaming_finished_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        total_time = round(time.perf_counter() - start_time, 4)
        logger.info(f"LLM Stream Finished. Total stream time: {total_time}s")

        # CRITICAL FIX: Detect when LLM outputs tool-call syntax as TEXT 
        # instead of using the structured tool_calls API.
        # The llama-3.1-8b model sometimes does this, outputting patterns like:
        #   function=verify_user>{"name": "...", "dob": "..."}
        #   <function=get_order_status></function>
        # We parse these and convert them into proper tool_calls.
        if not tool_calls and reply_content:
            rescued_calls = self._rescue_leaked_tool_calls(reply_content)
            if rescued_calls:
                tool_calls = rescued_calls
                logger.warning(
                    f"Rescued {len(rescued_calls)} leaked tool call(s) from LLM text output: "
                    f"{[tc['function']['name'] for tc in rescued_calls]}"
                )
                reply_content = ""  # Clear the leaked text

        assistant_msg = {"role": "assistant"}
        if reply_content:
            assistant_msg["content"] = reply_content
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls

        # Compile and log metrics
        ttft = round(first_token_time - start_time, 4) if first_token_time else 0.0
        generation_time = round(time.perf_counter() - first_token_time, 4) if first_token_time else total_time
        
        prompt_tokens = getattr(llm_usage, 'prompt_tokens', 0) if llm_usage else (history_tokens + summary_tokens + current_user_tokens)
        completion_tokens = getattr(llm_usage, 'completion_tokens', 0) if llm_usage else (len(reply_content) // 4)
        
        session_id = config.get("configurable", {}).get("thread_id", "unknown")
        
        # Check if it is the second LLM call (i.e. we are recovering from a tool call)
        is_second_llm = "No"
        if len(state.get("messages", [])) > 0 and state["messages"][-1].get("role") == "tool":
            is_second_llm = "Yes"
            
        tool_called_name = tool_calls[0]["function"]["name"] if tool_calls else "None"
        
        
        metrics = {
            "llm1_prompt_tokens": prompt_tokens,
            "llm1_completion_tokens": completion_tokens,
            "llm1_ttft": ttft,
            "llm1_generation_time": generation_time,
            "llm1_total_time": total_time,
            "tool_called": tool_called_name,
            "ttft": ttft,
            "generation_time": generation_time,
            "total_time": total_time
        }
        
        # Merge metrics into turn_metrics
        turn_metrics.update(metrics)

        return {"messages": [assistant_msg], "reply_text": self._sanitize_reply_text(reply_content), "turn_metrics": turn_metrics}

    async def _llm2_node(self, state: AgentState, config: RunnableConfig) -> dict:
        turn_metrics = state.get("turn_metrics", {})
        if "timing_prompt_assembly_start" not in turn_metrics:
            turn_metrics["timing_prompt_assembly_start"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
        session_id = config.get("configurable", {}).get("thread_id", "unknown")
        session = await self._sessions.get_or_create(session_id)
        client_id = getattr(session, "client_id", None)
        
        mapping = None
        if client_id is not None:
            try:
                mapping = await self._system_db.get_client_domain_mapping(client_id)
            except Exception as e:
                logger.error(f"Error fetching mapping for client {client_id}: {e}")

        logger.info(f"[_LLM2_NODE] Resolved session_id/thread_id: {session_id}, client_id: {client_id}")
        if mapping:
            logger.info(f"[_LLM2_NODE] Loaded domain mapping: {mapping.get('domain_name')}")
            base_prompt = mapping["system_prompt_llm2"]
        else:
            logger.info(f"[_LLM2_NODE] No domain mapping found, defaulting to Order Tracking.")
            base_prompt = get_prompts().get("cascade", {}).get("llm2_base", "You are a helpful assistant.")

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dynamic_prompt = f"{base_prompt}\n\nCURRENT SYSTEM DATE AND TIME: {current_time}"
        messages_to_send = [{"role": "system", "content": dynamic_prompt}]

        if state.get("verified") and state.get("customer"):
            messages_to_send.append({
                "role": "system",
                "content": (
                    f"CRITICAL STATE: You are ALREADY VERIFIED as {state['customer'].get('full_name', 'Unknown')}.\n"
                    f"DO NOT ask for name or DOB. Use the `get_order_status` tool to answer their queries immediately."
                )
            })

        if state.get("summary"):
            messages_to_send.append({
                "role": "system",
                "content": f"Here is a brief summary of the conversation so far: {state['summary']}"
            })
            messages_to_send.extend(state["messages"][-8:])
        else:
            messages_to_send.extend(state["messages"][-8:])

        use_tools = False
        llm_kwargs = dict(
            messages=messages_to_send,
            temperature=0.3,
        )
        if use_tools:
            llm_kwargs["tools"] = AGENT_TOOLS
            llm_kwargs["tool_choice"] = "auto"

        turn_metrics["timing_serialization_start"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        on_llm_token = config.get("configurable", {}).get("on_llm_token")
        
        reply_content = ""
        tool_calls = []
        
        start_time = time.perf_counter()
        first_token_time = None
        
        if "timing_prompt_assembly_end" not in turn_metrics:
            turn_metrics["timing_prompt_assembly_end"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        else:
            turn_metrics["timing_second_llm_send"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
        # --- LLM Metrics Tracking Variables ---
        llm_usage = None
        streaming_started_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        history_tokens = 0
        summary_tokens = 0
        current_user_tokens = 0
        
        # Estimate token lengths (roughly 4 chars = 1 token for basic counting)
        for msg in messages_to_send:
            content_len = len(str(msg.get("content", ""))) // 4
            if msg.get("role") == "system":
                summary_tokens += content_len
            elif msg == messages_to_send[-1] and msg.get("role") == "user":
                current_user_tokens += content_len
            else:
                history_tokens += content_len
        
        turn_metrics["timing_serialization_end"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        # ----------------------------------------
        
        # --- Industry Standard Stream Interceptor ---
        # We buffer the first few characters to detect if the LLM is leaking a tool call
        # as raw text. If it is, we mute the stream to TTS to prevent hallucinated code from being spoken.
        stream_open = False
        mute_stream = False
        held_text = ""
        
        async for chunk_type, chunk_data in self._groq_2.chat_completion_stream_with_tools(**llm_kwargs):
            if chunk_type == "timing":
                if chunk_data["event"] not in turn_metrics:
                    turn_metrics[chunk_data["event"]] = chunk_data["time"]
                continue
                
            if chunk_type == "usage":
                llm_usage = chunk_data
                continue
                
            if not first_token_time:
                first_token_time = time.perf_counter()
                logger.info(f"LLM TTFT internally measured: {round(first_token_time - start_time, 4)}s")
                tok_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                if "timing_first_token" not in turn_metrics:
                    turn_metrics["timing_first_token"] = tok_time
                else:
                    turn_metrics["timing_second_first_token"] = tok_time
            
            if chunk_type == "content":
                reply_content += chunk_data
                
                if mute_stream:
                    continue
                    
                if not stream_open:
                    held_text += chunk_data
                    # Check for leaked tool call signatures in the first few characters
                    text_lower = held_text.lower().strip()
                    
                    # If it definitely starts like a tool call, mute the stream permanently
                    if text_lower.startswith("function=") or text_lower.startswith("<function") or text_lower.startswith("<tool") or text_lower.startswith('{"name":') or text_lower.startswith('{"function"'):
                        mute_stream = True
                        continue
                        
                    # If it starts with an ambiguous character ('f', '<', '{'), buffer up to 15 chars to be sure
                    if text_lower.startswith("f") or text_lower.startswith("<") or text_lower.startswith("{"):
                        if len(text_lower) < 15:
                            continue  # Keep buffering
                            
                    # If we reach here, it's either not starting with a suspicious prefix, 
                    # or it broke the pattern (e.g. "for your order..."). Flush the buffer and open the stream.
                    stream_open = True
                    if on_llm_token and held_text:
                        try:
                            on_llm_token(held_text)
                        except Exception as e:
                            logger.debug(f"on_llm_token failed: {e}")
                    held_text = ""
                else:
                    if on_llm_token:
                        try:
                            on_llm_token(chunk_data)
                        except Exception as e:
                            logger.debug(f"on_llm_token failed: {e}")
            elif chunk_type == "tool_calls":
                tool_calls = chunk_data

        streaming_finished_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        total_time = round(time.perf_counter() - start_time, 4)
        logger.info(f"LLM Stream Finished. Total stream time: {total_time}s")

        # CRITICAL FIX: Detect when LLM outputs tool-call syntax as TEXT 
        # instead of using the structured tool_calls API.
        # The llama-3.1-8b model sometimes does this, outputting patterns like:
        #   function=verify_user>{"name": "...", "dob": "..."}
        #   <function=get_order_status></function>
        # We parse these and convert them into proper tool_calls.
        if not tool_calls and reply_content:
            rescued_calls = self._rescue_leaked_tool_calls(reply_content)
            if rescued_calls:
                tool_calls = rescued_calls
                logger.warning(
                    f"Rescued {len(rescued_calls)} leaked tool call(s) from LLM text output: "
                    f"{[tc['function']['name'] for tc in rescued_calls]}"
                )
                reply_content = ""  # Clear the leaked text

        assistant_msg = {"role": "assistant"}
        if reply_content:
            assistant_msg["content"] = reply_content
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls

        # Compile and log metrics
        ttft = round(first_token_time - start_time, 4) if first_token_time else 0.0
        generation_time = round(time.perf_counter() - first_token_time, 4) if first_token_time else total_time
        
        prompt_tokens = getattr(llm_usage, 'prompt_tokens', 0) if llm_usage else (history_tokens + summary_tokens + current_user_tokens)
        completion_tokens = getattr(llm_usage, 'completion_tokens', 0) if llm_usage else (len(reply_content) // 4)
        
        session_id = config.get("configurable", {}).get("thread_id", "unknown")
        
        # Check if it is the second LLM call (i.e. we are recovering from a tool call)
        is_second_llm = "No"
        if len(state.get("messages", [])) > 0 and state["messages"][-1].get("role") == "tool":
            is_second_llm = "Yes"
            
        tool_called_name = tool_calls[0]["function"]["name"] if tool_calls else "None"
        
        
        metrics = {
            "llm2_prompt_tokens": prompt_tokens,
            "llm2_completion_tokens": completion_tokens,
            "llm2_ttft": ttft,
            "llm2_generation_time": generation_time,
            "llm2_total_time": total_time,
            "ttft": ttft,
            "generation_time": generation_time,
            "total_time": total_time
        }
        
        # Merge metrics into turn_metrics
        turn_metrics.update(metrics)

        return {"messages": [assistant_msg], "reply_text": self._sanitize_reply_text(reply_content), "turn_metrics": turn_metrics}


    @staticmethod
    def _rescue_leaked_tool_calls(text: str) -> list[dict]:
        import uuid
        calls = []
        
        # Pattern 1: function=verify_user>{"name": "...", "dob": "..."}
        m1 = re.search(r'function\s*=\s*(verify_user)\s*>\s*(\{.*?\})', text, re.DOTALL)
        if m1:
            calls.append({
                "id": "call_" + str(uuid.uuid4())[:8],
                "type": "function",
                "function": {
                    "name": m1.group(1),
                    "arguments": m1.group(2)
                }
            })
            return calls
            
        # Pattern 2: function=get_order_status>
        m2 = re.search(r'function\s*=\s*(get_order_status)\s*>', text)
        if m2:
            calls.append({
                "id": "call_" + str(uuid.uuid4())[:8],
                "type": "function",
                "function": {
                    "name": m2.group(1),
                    "arguments": "{}"
                }
            })
            return calls
            
        return calls

    @staticmethod
    def _dob_found_in_user_messages(messages: list, dob: str) -> bool:
        """Check if a date-of-birth-like string actually appears in user messages.
        
        This prevents the LLM from hallucinating a DOB that the user never spoke.
        We look for date-like patterns in user messages (digits, month names, slashes, dashes).
        """
        import calendar
        
        # Extract all user message texts
        user_texts = []
        for msg in messages:
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if role == "user" and content:
                user_texts.append(content.lower())
        
        if not user_texts:
            return False
        
        combined_user_text = " ".join(user_texts)
        
        # Check 1: Look for any date-like numeric patterns in user messages
        # Patterns like: MM/DD/YYYY, DD-MM-YYYY, YYYY-MM-DD, MM.DD.YYYY, etc.
        date_patterns = [
            re.compile(r'\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}'),  # MM/DD/YYYY or DD-MM-YYYY variants
            re.compile(r'\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}'),     # YYYY-MM-DD variants
        ]
        
        has_date_pattern = any(p.search(combined_user_text) for p in date_patterns)
        
        # Check 2: Look for month names (January, Jan, etc.) combined with numbers
        month_names = [m.lower() for m in calendar.month_name[1:]] + [m.lower() for m in calendar.month_abbr[1:]]
        has_month_name = any(m in combined_user_text for m in month_names if m)
        has_numbers = bool(re.search(r'\d{1,4}', combined_user_text))
        has_verbal_date = has_month_name and has_numbers
        
        # Check 3: Look for keywords indicating DOB context
        dob_keywords = ["birth", "born", "dob", "birthday", "date of birth"]
        has_dob_keyword = any(kw in combined_user_text for kw in dob_keywords)
        
        # The user must have provided SOME date-like information
        return has_date_pattern or has_verbal_date or (has_dob_keyword and has_numbers)

    @staticmethod
    def _name_found_in_user_messages(messages: list, name: str) -> bool:
        """Check if the name passed to verify_user was actually spoken by the user.
        
        This prevents the LLM from hallucinating a name when the user only provided DOB.
        We check that at least the major parts of the name appear in user messages.
        """
        # Extract all user message texts
        user_texts = []
        for msg in messages:
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if role == "user" and content:
                user_texts.append(content.lower())
        
        if not user_texts:
            return False
        
        combined_user_text = " ".join(user_texts)
        
        # Split the name into parts and check that each significant part appears in user messages
        # e.g., for "Rohit Sharma", check that both "rohit" and "sharma" appear
        name_parts = [p.strip().lower() for p in name.split() if len(p.strip()) > 1]
        
        if not name_parts:
            return False
        
        # All significant parts of the name must appear in user messages
        return all(part in combined_user_text for part in name_parts)

    async def _verify_tool_node(self, state: AgentState, config: RunnableConfig) -> dict:
        turn_metrics = state.get("turn_metrics", {})
        turn_metrics["timing_tool_start"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        session_id = config.get("configurable", {}).get("thread_id", "unknown")
        session = await self._sessions.get_or_create(session_id)
        client_id = getattr(session, "client_id", None)
        
        db_client = None
        mapping = None
        if client_id is not None:
            try:
                db_config = await self._system_db.get_client_db_config(client_id)
                mapping = await self._system_db.get_client_domain_mapping(client_id)
                if db_config and mapping:
                    db_client = DynamicDbClient(db_config)
            except Exception as e:
                logger.error(f"Failed to load dynamic DB client for client {client_id}: {e}")

        last_msg = state["messages"][-1]
        updates = {"messages": [], "turn_metrics": turn_metrics}
        
        for tc in last_msg.get("tool_calls", []):
            tool_name = tc["function"]["name"]
            
            if tool_name == "verify_user" or tool_name.startswith("verify"):
                try:
                    args = json.loads(tc["function"]["arguments"])
                except Exception:
                    args = {}
                name = args.get("name", "")
                dob = args.get("dob", "")
                
                # SECURITY CHECK: Enforce that both name and dob are present
                if not name and not dob:
                    result_str = json.dumps({
                        "error": "MISSING_INFORMATION",
                        "message": "You MUST explicitly ask the user for both their full name and date of birth. Do NOT guess or fabricate any information."
                    })
                    updates["messages"].append({"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": result_str})
                    continue
                elif name and not dob:
                    result_str = json.dumps({
                        "error": "MISSING_DOB",
                        "message": "Missing date of birth. You MUST explicitly ask the user for their date of birth before verifying. Do NOT guess a DOB."
                    })
                    updates["messages"].append({"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": result_str})
                    continue
                elif dob and not name:
                    result_str = json.dumps({
                        "error": "MISSING_NAME",
                        "message": "Missing full name. You MUST explicitly ask the user for their full name before verifying."
                    })
                    updates["messages"].append({"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": result_str})
                    continue
                
                # ANTI-HALLUCINATION CHECK: Verify the DOB was actually spoken by the user
                all_messages = state.get("messages", [])
                if not self._dob_found_in_user_messages(all_messages, dob):
                    logger.warning(
                        f"DOB hallucination blocked: LLM tried to verify with dob='{dob}' "
                        f"but no date was found in user messages. Name='{name}'"
                    )
                    result_str = json.dumps({
                        "error": "DOB_NOT_PROVIDED_BY_USER",
                        "message": (
                            "REJECTED: The date of birth you provided was NOT spoken by the user. "
                            "You appear to have fabricated or guessed the DOB. This is NOT allowed. "
                            "You MUST ask the user: 'Could you please tell me your date of birth?' "
                            "and wait for their actual response before calling verify_user again."
                        )
                    })
                    updates["messages"].append({"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": result_str})
                    continue
                
                # ANTI-HALLUCINATION CHECK: Verify the name was actually spoken by the user
                if not self._name_found_in_user_messages(all_messages, name):
                    logger.warning(
                        f"Name hallucination blocked: LLM tried to verify with name='{name}' "
                        f"but the name was not found in user messages."
                    )
                    result_str = json.dumps({
                        "error": "NAME_NOT_PROVIDED_BY_USER",
                        "message": (
                            "REJECTED: The name you provided was NOT spoken by the user. "
                            "You appear to have fabricated or guessed the name. This is NOT allowed. "
                            "You MUST ask the user: 'Could you please tell me your full name?' "
                            "and wait for their actual response before calling verify_user again."
                        )
                    })
                    updates["messages"].append({"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": result_str})
                    continue
                
                # SECURITY CHECK: Prevent overwriting an already verified session with a different user
                current_verified = state.get("verified", False)
                current_customer = state.get("customer")
                
                if current_verified and current_customer:
                    existing_name = state.get("user_name", "")
                    if existing_name.lower() != name.lower():
                        result_str = json.dumps({
                            "verified": False,
                            "error": "SECURITY_VIOLATION",
                            "message": f"CRITICAL ERROR: This session is permanently locked to {existing_name}. You CANNOT verify {name}. You MUST explicitly tell the user: 'I can only provide information for {existing_name}.' Do NOT call any other tools."
                        })
                    else:
                        result_str = json.dumps({
                            "verified": True,
                            "message": f"You are already verified as {existing_name}. You do not need to verify again. You MUST explicitly tell the user they are already verified."
                        })
                    
                    updates["messages"].append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc["function"]["name"],
                        "content": result_str
                    })
                    continue
                
                verified = False
                customer = None
                records = []
                
                if db_client and mapping:
                    try:
                        # Clean, normalize and lowercase the name to match LOWER(full_name) = ?
                        name_clean = name.strip().rstrip('.').lower()
                        
                        # Clean and normalize the DOB string
                        dob_norm = dob
                        import re
                        dob_clean = re.sub(r'(st|nd|rd|th)', '', dob.lower())
                        dob_clean = dob_clean.replace(',', '').strip()
                        
                        parsed_date = None
                        # 1) YYYY-MM-DD or YYYY/MM/DD
                        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", dob_clean)
                        if m:
                            try:
                                parsed_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                            except ValueError:
                                pass
                        
                        if not parsed_date:
                            # 2) MM/DD/YYYY or MM-DD-YYYY
                            m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", dob_clean)
                            if m:
                                try:
                                    parsed_date = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                                except ValueError:
                                    pass
                        
                        if not parsed_date:
                            # 3) Natural language: "15 may 1990", "may 15 1990"
                            for fmt in ("%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
                                try:
                                    parsed_date = datetime.strptime(dob_clean, fmt).date()
                                    break
                                except ValueError:
                                    continue
                        
                        if not parsed_date:
                            try:
                                parsed_date = date.fromisoformat(dob_clean)
                            except ValueError:
                                pass
                        
                        if parsed_date:
                            dob_norm = parsed_date.isoformat()
                        
                        logger.info(f"name: {name_clean}, dob input: {dob}, dob normalized: {dob_norm}")
                        logger.info(f"verification_query: {mapping['verification_query']}")
                        
                        rows = await db_client.execute_query(mapping["verification_query"], (name_clean, dob_norm))
                        logger.info(f"rows found:  {rows}")
                        if rows:
                            verified = True
                            customer = rows[0]
                            # Format dates in patient/customer dict
                            for k, v in list(customer.items()):
                                if hasattr(v, "isoformat"):
                                    customer[k] = v.isoformat()
                            
                            raw_records = await db_client.execute_query(mapping["data_query"], (customer["id"],))
                            records = []
                            for r in raw_records:
                                item = dict(r)
                                for k, v in list(item.items()):
                                    if hasattr(v, "isoformat"):
                                        item[k] = v.isoformat()
                                records.append(item)
                    except Exception as e:
                        logger.error(f"Error executing tenant verification query: {e}")
                else:
                    # Fallback to local VerificationService and OrderService
                    verification = await self._verification.verify(name, dob)
                    if verification.verified and verification.customer:
                        verified = True
                        customer = verification.customer
                        raw_orders = await self._orders.get_orders(customer.get("id"))
                        records = raw_orders.get("recent_orders", [])

                if verified and customer:
                    updates["verified"] = True
                    updates["user_name"] = name
                    updates["dob"] = dob
                    updates["customer"] = customer
                    updates["orders"] = records
                    result_str = json.dumps({
                        "verified": True, 
                        "message": "Account verified successfully.",
                        "customer_name": customer.get("full_name"),
                        "records": records
                    })
                else:
                    updates["verified"] = False
                    updates["user_name"] = None
                    updates["dob"] = None
                    updates["customer"] = None
                    result_str = json.dumps({
                        "verified": False, 
                        "message": "CRITICAL: No matching account found. The provided Name and DOB are incorrect. You MUST explicitly tell the user the verification failed, drop the previous name and DOB, and ask them to provide BOTH their full name and date of birth again."
                    })
                
                updates["messages"].append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": result_str
                })
            else:
                # Dynamic data query for matching domains
                if not state.get("verified") or not state.get("customer"):
                    result_str = json.dumps({"error": "User not verified. Please verify user first."})
                else:
                    records = []
                    if db_client and mapping:
                        try:
                            raw_records = await db_client.execute_query(mapping["data_query"], (state["customer"]["id"],))
                            records = []
                            for r in raw_records:
                                item = dict(r)
                                for k, v in list(item.items()):
                                    if hasattr(v, "isoformat"):
                                        item[k] = v.isoformat()
                                records.append(item)
                        except Exception as e:
                            logger.error(f"Error executing tenant data query: {e}")
                    else:
                        raw_orders = await self._orders.get_orders(state["customer"]["id"])
                        records = raw_orders.get("recent_orders", [])
                    
                    updates["orders"] = records
                    result_str = json.dumps({
                        "customer_name": state["customer"].get("full_name", "Unknown"),
                        "records": records
                    })
                
                updates["messages"].append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": result_str
                })
        
        turn_metrics["timing_tool_end"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        return updates

    async def handle_user_text(
        self, session_id: str, user_text: str, on_llm_token: Optional[Callable[[str], None]] = None
    ) -> ConversationResult:
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        turn_metrics = {}
        turn_metrics["timing_memory_retrieval_start"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Get or create the session state (for compatibility with legacy SessionManager)
        session = await self._sessions.get_or_create(session_id)
        
        turn_metrics["timing_memory_retrieval_end"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        config = {"configurable": {"thread_id": session_id, "on_llm_token": on_llm_token}}
        
        turn_metrics["timing_state_update_start"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Initialize graph state if empty
        graph_state = await self._graph.aget_state(config)
        if not graph_state.values:
            # Sync initial state from legacy SessionState if needed, but we start fresh
            await self._graph.aupdate_state(config, {
                "verified": session.verified,
                "user_name": session.user_name,
                "dob": session.dob,
                "customer": {"id": session.customer_id, "full_name": session.customer_name} if session.customer_id else None,
                "orders": session.orders if hasattr(session, "orders") else [],
                "messages": [],
                "summary": None,
                "turn_metrics": turn_metrics,
            })
        else:
            await self._graph.aupdate_state(config, {"turn_metrics": turn_metrics})
            
        turn_metrics["timing_state_update_end"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        turn_metrics["timing_langgraph_invoke"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
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
            session.customer_name = state_values["customer"].get("full_name", state_values["customer"].get("name"))
            session.orders = state_values.get("orders", [])
        
        session.last_response = reply_text
        if user_text:
            session.add_turn("user", user_text, SESSION_MAX_TURNS)
        session.add_turn("assistant", reply_text, SESSION_MAX_TURNS)
        await self._sessions.update(session)
        
        # --- Save history to folder (background â€” non-blocking) ---
        async def _save_history_bg():
            try:
                history_dir = os.path.join(os.getcwd(), "histories")
                os.makedirs(history_dir, exist_ok=True)
                history_file = os.path.join(history_dir, f"{session_id}.json")
                
                history_data = []
                for msg in state_values.get("messages", []):
                    if hasattr(msg, "model_dump"):
                        history_data.append(msg.model_dump())
                    elif isinstance(msg, dict):
                        history_data.append(msg)
                    else:
                        history_data.append({"role": getattr(msg, "role", "unknown"), "content": getattr(msg, "content", str(msg))})
                
                def _write():
                    with open(history_file, "w", encoding="utf-8") as f:
                        json.dump(history_data, f, indent=2)
                await asyncio.to_thread(_write)
            except Exception as e:
                logger.error(f"Failed to save history for {session_id}: {e}")
        asyncio.create_task(_save_history_bg())
        
        timings["total"] = round(time.perf_counter() - t0, 4)

        # Trigger background summarization
        asyncio.create_task(self._summarize_session_async(session_id))

        final_turn_metrics = state_values.get("turn_metrics", {})
        # Merge local timings (e.g. langgraph_invoke) that were added after aupdate_state
        final_turn_metrics.update(turn_metrics)

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
            turn_metrics=final_turn_metrics,
        )

    async def _summarize_session_async(self, session_id: str):
        try:
            config = {"configurable": {"thread_id": session_id}}
            graph_state = await self._graph.aget_state(config)
            if not graph_state.values:
                return
                
            messages = graph_state.values.get("messages", [])
            # Only summarize if we have more than 6 messages (approx 3 user turns)
            if len(messages) <= 6:
                return
                
            # Create a separate Groq client instance using the summary API key
            summary_api_key = os.getenv("GROQ_SUMMARY_API_KEY")
            summary_model = os.getenv("SUMMARY_MODEL", "llama-3.1-8b-instant")
            
            if not summary_api_key:
                logger.warning("GROQ_SUMMARY_API_KEY not set, skipping summarization.")
                return
                
            # Force the summarizer to use Groq, even if main LLM is OpenAI
            summary_groq = GroqClient(api_key=summary_api_key, provider="groq")
            
            # We want to summarize everything EXCEPT the last 7 messages
            messages_to_summarize = messages[:-7]
            
            text_to_summarize = ""
            for msg in messages_to_summarize:
                role = msg.get("role", "unknown") if isinstance(msg, dict) else getattr(msg, "role", "unknown")
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                
                # Exclude tool calls and empty content to save tokens
                if role == "tool" or not content:
                    continue
                text_to_summarize += f"{role}: {content}\n"
                
            if not text_to_summarize.strip():
                await summary_groq.close()
                return
                
            prompt = [
                {"role": "system", "content": "Summarize the conversation. You MUST retain ALL specific order IDs (e.g., ORD-...), dates, tracking numbers, and verified names exactly as they appeared. Do not omit any IDs. Keep it under 50 words if possible."},
                {"role": "user", "content": f"Conversation:\n{text_to_summarize}"}
            ]
            
            summary = await summary_groq.chat_completion(
                messages=prompt,
                model=summary_model,
                temperature=0.1,
                max_tokens=150,
                stage="summarizer"
            )
            
            await summary_groq.close()
            
            # Update the graph state with the new summary
            if summary:
                mem_input = 0
                mem_output = 0
                if hasattr(summary_groq, 'last_usage') and summary_groq.last_usage:
                    mem_input = summary_groq.last_usage.get('prompt_tokens', 0)
                    mem_output = summary_groq.last_usage.get('completion_tokens', 0)
                    
                await self._graph.aupdate_state(config, {
                    "summary": summary,
                    "memory_tokens_input": mem_input,
                    "memory_tokens_output": mem_output
                })
                logger.info(f"Session {session_id} background summary generated: {summary} (Tokens: {mem_input} in, {mem_output} out)")
            
        except Exception as e:
            logger.error(f"Background summarization failed for {session_id}: {e}")
