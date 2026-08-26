import os
import json
import logging
from typing import Dict, Any, List, Optional

from app.groq_client import GroqClient
from app.database import DatabaseClient
from app.system_database import SystemDatabase
from app.memory.memory_manager import MemoryManager
from app.utils.prompt_loader import get_prompts

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service to process conversation analytics, summaries/intents, and continuous learning."""

    def __init__(self, db_client: DatabaseClient, system_db: Optional[SystemDatabase] = None):
        self.db = db_client
        self.system_db = system_db or SystemDatabase()
        self.memory_manager = MemoryManager(self.system_db)
        self.api_key = os.getenv("GROQ_SUMMARY_API_KEY") or os.getenv("GROQ_API_KEY")
        self.model = os.getenv("SUMMARY_MODEL", "llama-3.1-8b-instant")
        
        # Initialize Groq client only if API key is present
        self.groq = GroqClient(api_key=self.api_key, provider="groq") if self.api_key else None

    async def process_call_analytics(
        self,
        session_id: str,
        pipeline_mode: str,
        history: List[Dict[str, Any]],
        total_input_tokens: int,
        total_output_tokens: int,
        average_latency: float,
        user_id: int = None,
        client_id: Any = None,
        domain: str = None,
        domain_id: Optional[int] = None,
        caller_identifier: Optional[str] = None
    ) -> None:
        """
        Process the completed call by generating a summary/intent, storing analytics,
        and triggering the Continuous Learning System 2 post-call flywheel.
        """
        try:
            summary = "Summary not generated"
            intent = "unknown"
            summary_input_tokens = 0
            summary_output_tokens = 0

            # Generate summary and intent using Groq if configured and history exists
            if self.groq and len(history) > 0:
                text_to_summarize = ""
                for msg in history:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    
                    if role == "tool" or not content:
                        continue
                    text_to_summarize += f"{role}: {content}\n"
                
                if text_to_summarize.strip():
                    prompts_yaml = get_prompts()
                    system_content = prompts_yaml.get("summarization", {}).get("conversation_summary", "Summarize the call.")
                    prompt = [
                        {
                            "role": "system", 
                            "content": system_content
                        },
                        {"role": "user", "content": f"Conversation:\n{text_to_summarize}"}
                    ]
                    
                    try:
                        # We use chat_completion here and parse JSON
                        response_text = await self.groq.chat_completion(
                            messages=prompt,
                            model=self.model,
                            temperature=0.3,
                            max_tokens=400,
                            stage="analytics_summarizer",
                            response_format={"type": "json_object"}
                        )
                        
                        # Retrieve usage from the client if tracked
                        if hasattr(self.groq, 'last_usage') and self.groq.last_usage:
                            summary_input_tokens = self.groq.last_usage.get('prompt_tokens', 0)
                            summary_output_tokens = self.groq.last_usage.get('completion_tokens', 0)
                        else:
                            summary_input_tokens = len(text_to_summarize) // 4
                            summary_output_tokens = len(response_text) // 4

                        if response_text:
                            # Clean up potential markdown if the model ignored instructions
                            clean_text = response_text.replace("```json", "").replace("```", "").strip()
                            data = json.loads(clean_text)
                            summary = data.get("summary", "No summary provided")
                            intent = data.get("intent", "unknown")
                    except Exception as e:
                        logger.error(f"Failed to generate summary/intent for {session_id}: {e}")

            # Calculate token costs
            # Gemini: $3 per 1M input, $12 per 1M output
            gemini_input_cost = (total_input_tokens / 1_000_000) * 3.0
            gemini_output_cost = (total_output_tokens / 1_000_000) * 12.0
            
            # Groq: $0 (as requested)
            groq_input_cost = 0.0
            groq_output_cost = 0.0
            
            total_input_cost = gemini_input_cost + groq_input_cost
            total_output_cost = gemini_output_cost + groq_output_cost
            total_cost = total_input_cost + total_output_cost

            # Prepare the log record
            log_data = {
                "session_id": session_id,
                "user_id": user_id,
                "client_id": str(client_id) if client_id is not None else None,
                "domain": domain,
                "pipeline_mode": pipeline_mode,
                "history": history,
                "summary": summary,
                "intent": intent,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_input_output_tokens": total_input_tokens + total_output_tokens,
                "summary_input_tokens": summary_input_tokens,
                "summary_output_tokens": summary_output_tokens,
                "summary_input_output_tokens": summary_input_tokens + summary_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens + summary_input_tokens + summary_output_tokens,
                "average_latency": average_latency,
                "total_input_cost": total_input_cost,
                "total_output_cost": total_output_cost,
                "total_cost": total_cost
            }

            # Save to database
            success = await self.db.save_call_log(log_data)
            if success:
                logger.info(f"Successfully saved call analytics for session {session_id}")
            else:
                logger.error(f"Failed to save call analytics for session {session_id} to DB")

            # --- Continuous Learning: System 2 Asynchronous Post-Call Flywheel ---
            try:
                clean_client_id = int(client_id) if (client_id is not None and str(client_id).isdigit()) else None
                resolved_caller = caller_identifier or (str(user_id) if user_id else None)

                await self.memory_manager.process_post_call_learning(
                    session_id=session_id,
                    history=history,
                    domain=domain,
                    client_id=clean_client_id,
                    domain_id=domain_id,
                    caller_identifier=resolved_caller
                )
                logger.info(f"[ContinuousLearning] Successfully executed post-call flywheel for session {session_id}")
            except Exception as cl_err:
                logger.error(f"[ContinuousLearning] Error in post-call learning for {session_id}: {cl_err}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in process_call_analytics for session {session_id}: {e}")

