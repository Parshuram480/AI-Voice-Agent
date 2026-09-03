import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiChatService:
    """Service to handle standard text-based chatbot loops using Gemini."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key is not configured.")
        
        self.client = genai.Client(api_key=self.api_key)
        # Dedicated model for text chat, leaving GEMINI_LIVE_MODEL untouched
        self.model = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")
        logger.info(f"Initialized GeminiChatService with model: {self.model}")

    async def handle_chat_message(
        self,
        message: str,
        system_prompt: str,
        tool_declarations: list,
        executor,
        session_state: dict,
        dynamic_config: dict = None
    ) -> dict:
        import uuid
        
        # Build contents history from session conversation turns (limited to last 6 turns to optimize rate limits)
        history_turns = session_state.get("conversation_history", [])
        if len(history_turns) > 6:
            history_turns = history_turns[-6:]

        gemini_history = []
        for turn in history_turns:
            role = "user" if turn.role == "user" else "model"
            gemini_history.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=turn.text)]
                )
            )

        # Append current user message (if starting, mock a hello to trigger the system prompt's B2B hook / pitch)
        user_msg_text = "Hello" if message == "__START__" else message
        gemini_history.append(
            types.Content(
                role="user",
                parts=[types.Part(text=user_msg_text)]
            )
        )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[{"function_declarations": tool_declarations}] if tool_declarations else None,
            temperature=0.4,
        )

        loop_count = 0
        reply_text = ""
        current_intent = session_state.get("current_intent", "unknown")
        
        chat_state = {
            "client_id": session_state.get("client_id"),
            "domain_id": session_state.get("domain_id"),
            "verified": session_state.get("verified", False),
            "identity_id": session_state.get("identity_id"),
            "session_id": session_state.get("session_id"),
            "domain": session_state.get("domain"),
            "user_details": session_state.get("user_details"),
            "records": session_state.get("records", []),
            "orders": session_state.get("orders", []),
            "customer": session_state.get("customer"),
        }

        while loop_count < 5:
            loop_count += 1
            # Try to generate content, falling back to other models if a 503 or overload is raised
            response = None
            models_to_try = [self.model]
            default_fallbacks = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash","gemini-3.7-flash"]
            for m in default_fallbacks:
                if m != self.model:
                    models_to_try.append(m)

            last_error = None
            for active_model in models_to_try:
                try:
                    logger.info(f"Generating content with model: {active_model}")
                    response = self.client.models.generate_content(
                        model=active_model,
                        contents=gemini_history,
                        config=config,
                    )
                    # If successful, remember this active model for the rest of this session
                    self.model = active_model
                    break
                except Exception as e:
                    err_msg = str(e)
                    # 1. Handle HTTP 429 Rate Limit (RESOURCE_EXHAUSTED) with a 2-second backoff sleep and retry
                    if any(term in err_msg.lower() for term in ("429", "resource_exhausted", "quota", "limit")):
                        import asyncio
                        logger.warning(f"Rate limit hit on model {active_model}. Sleeping 2 seconds before retry...")
                        await asyncio.sleep(2)
                        try:
                            logger.info(f"Retrying content generation with model: {active_model} after rate limit sleep")
                            response = self.client.models.generate_content(
                                model=active_model,
                                contents=gemini_history,
                                config=config,
                            )
                            self.model = active_model
                            break
                        except Exception as retry_err:
                            err_msg = str(retry_err)
                            logger.warning(f"Retry failed on model {active_model} after rate limit sleep: {retry_err}")
                            last_error = retry_err

                    # 2. Handle HTTP 503 Spikes or generic model overloads by continuing to next fallback model
                    if any(term in err_msg.lower() for term in ("503", "unavailable", "overloaded", "demand", "temporary")):
                        logger.warning(f"Model {active_model} is unavailable. Retrying with fallback. Error: {err_msg}")
                        last_error = e
                        continue
                    else:
                        raise e
            else:
                if last_error:
                    raise last_error

            function_calls = response.function_calls
            if not function_calls:
                reply_text = response.text
                break

            # Append model response initiating function call to history
            gemini_history.append(response.candidates[0].content)

            # Execute function calls
            tool_responses = []
            for fc in function_calls:
                fc_name = fc.name
                fc_args = fc.args
                fc_id = fc.id or str(uuid.uuid4())[:8]

                if fc_name.startswith("verify_") or fc_name in ("verify_user", "get_order_status"):
                    current_intent = fc_name

                if executor:
                    tool_res = await executor.execute(fc_id, fc_name, fc_args, chat_state)
                    tool_responses.append(tool_res)

                    # Dynamic state parsing based on executor response
                    resp_dict = getattr(tool_res, "response", {}) or {}
                    # 1. Verification handler
                    if fc_name.startswith("verify_") and resp_dict.get("verified"):
                        user_details = resp_dict.get("user_details", {})
                        chat_state["verified"] = True
                        chat_state["user_details"] = user_details
                        
                        # Dynamically locate primary full name column configured in database settings
                        name_col = "name"
                        if dynamic_config and "identity" in dynamic_config:
                            name_col = dynamic_config["identity"].get("name_column", "name")
                        
                        name_val = user_details.get(name_col, "Verified Customer")
                        chat_state["customer"] = {
                            "id": chat_state.get("identity_id"),
                            "full_name": name_val
                        }
                    # 2. Linked Records handler
                    elif "results" in resp_dict:
                        results = resp_dict.get("results", [])
                        chat_state["records"] = results
                        chat_state["orders"] = results
                else:
                    tool_responses.append(
                        types.FunctionResponse(
                            name=fc_name,
                            id=fc_id,
                            response={"error": "Dynamic executor not configured on the server."}
                        )
                    )

            # Append tool responses to history
            parts = [types.Part(function_response=tr) for tr in tool_responses]
            gemini_history.append(
                types.Content(
                    role="user",
                    parts=parts
                )
            )

        return {
            "reply_text": reply_text or "Could you please rephrase?",
            "intent": current_intent,
            "chat_state": chat_state
        }
