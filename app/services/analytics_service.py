import os
import json
import logging
from typing import Dict, Any, List

from app.groq_client import GroqClient
from app.database import DatabaseClient

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service to process conversation analytics and generate summaries/intents."""

    def __init__(self, db_client: DatabaseClient):
        self.db = db_client
        self.api_key = os.getenv("GROQ_SUMMARY_API_KEY")
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
        user_id: int = None
    ) -> None:
        """
        Process the completed call by generating a summary/intent and storing it in DB.
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
                    prompt = [
                        {
                            "role": "system", 
                            "content": (
                                "You are an AI assistant that analyzes customer service calls. "
                                "Read the conversation and return a JSON object with EXACTLY two keys: 'summary' and 'intent'.\n"
                                "1. 'summary': A detailed, human-like professional summary of the entire conversation capturing all key details, context, and outcomes. Write it as a natural paragraph around 3-5 sentences.\n"
                                "2. 'intent': A 1-4 word classification of the user's primary goal. Choose from or adapt this taxonomy:\n"
                                "   - Core E-commerce: 'Order Status', 'Order Modification', 'Returns/Refunds', 'Product Inquiry', 'Account/Billing'\n"
                                "   - Support: 'Authentication', 'Escalation to Human', 'Technical Support'\n"
                                "   - Behavior: 'Small Talk', 'Frustration/Complaint', 'Irrelevant/Prank', 'Silent/Dropped'\n"
                                "   If none fit perfectly, create a highly descriptive 1-4 word intent.\n"
                                "CRITICAL: You must output ONLY a valid JSON object. Use double quotes around all keys and string values."
                            )
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
                            # Approximate tokens if last_usage is not captured by GroqClient 
                            # (Depending on GroqClient implementation, we might just estimate)
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

            # Prepare the log record
            log_data = {
                "session_id": session_id,
                "user_id": user_id,
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
                "average_latency": average_latency
            }

            # Save to database
            success = await self.db.save_call_log(log_data)
            if success:
                logger.info(f"Successfully saved call analytics for session {session_id}")
            else:
                logger.error(f"Failed to save call analytics for session {session_id} to DB")

        except Exception as e:
            logger.error(f"Error in process_call_analytics for session {session_id}: {e}")
        finally:
            if self.groq:
                await self.groq.close()
