"""LLM-as-a-Judge Evaluator Engine for Post-Call Continuous Learning.

Evaluates conversation transcripts using domain rubrics:
- Task Completion Score (0 - 100)
- Friction Score (1 - 5)
- Tool & Grounding Accuracy Score (0 - 100)
- Detected Agent Mistakes
- Actionable Behavioral Lessons
- Durable Caller Facts & Preference Extraction
"""

import os
import json
import logging
import re
from typing import Dict, Any, List, Optional

from app.groq_client import GroqClient
from app.memory.pii_sanitizer import PIISanitizer
from app.utils.prompt_loader import get_prompts

logger = logging.getLogger(__name__)


class EvaluatorJudge:
    """Evaluates completed voice call transcripts against rubrics and extracts durable facts."""

    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        model: Optional[str] = None,
        sanitizer: Optional[PIISanitizer] = None,
    ):
        self.api_key = (
            os.getenv("GROQ_SUMMARY_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or ""
        )
        self.model = model or os.getenv("SUMMARY_MODEL", "llama-3.1-8b-instant")
        self.groq = groq_client or (GroqClient(api_key=self.api_key, provider="groq") if self.api_key else None)
        self.sanitizer = sanitizer or PIISanitizer()

    async def evaluate_call(
        self,
        session_id: str,
        history: List[Dict[str, Any]],
        domain: Optional[str] = None,
        client_id: Optional[int] = None,
        domain_id: Optional[int] = None,
        caller_identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Runs post-call quality evaluation on a conversation transcript.
        
        Returns structured evaluation dictionary ready for PostgreSQL storage.
        """
        fallback_evaluation = {
            "session_id": session_id,
            "client_id": client_id,
            "domain_id": domain_id,
            "task_completion_score": 0,
            "friction_score": 1,
            "tool_accuracy_score": 0,
            "evaluation_details": {"reasoning": "No evaluation available."},
            "mistakes_detected": [],
            "actionable_lessons": [],
            "extracted_facts": {},
        }

        if not history or not isinstance(history, list):
            logger.info(f"[EvaluatorJudge] No transcript history provided for session {session_id}.")
            return fallback_evaluation

        # 1. Format raw transcript from history
        transcript_lines: List[str] = []
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "tool" or not content:
                continue
            transcript_lines.append(f"{role.capitalize()}: {content}")

        if not transcript_lines:
            logger.info(f"[EvaluatorJudge] Empty transcript content for session {session_id}.")
            return fallback_evaluation

        raw_transcript = "\n".join(transcript_lines)

        # 2. Sanitize PII from transcript before evaluation
        sanitized_transcript = self.sanitizer.sanitize_text(raw_transcript)

        if not self.groq:
            logger.warning("[EvaluatorJudge] GroqClient not configured (missing API key). Returning fallback evaluation.")
            return fallback_evaluation

        # 3. Load prompt rubric
        prompts_yaml = get_prompts()
        judge_rubric = prompts_yaml.get("evaluation", {}).get(
            "call_judge_rubric",
            "Evaluate the call and return a JSON object with scores, reasoning, mistakes, lessons, and extracted_facts."
        )

        domain_str = domain or "general"
        caller_str = caller_identifier or "unknown"

        messages = [
            {"role": "system", "content": judge_rubric},
            {
                "role": "user",
                "content": f"Operational Domain: {domain_str}\nCaller Identifier: {caller_str}\n\nSanitized Call Transcript:\n{sanitized_transcript}"
            }
        ]

        try:
            response_text = await self.groq.chat_completion(
                messages=messages,
                model=self.model,
                temperature=0.1,
                max_tokens=2048,
                stage="evaluator_judge",
                response_format={"type": "json_object"},
            )


            if not response_text:
                logger.warning(f"[EvaluatorJudge] Empty response returned for session {session_id}.")
                return fallback_evaluation

            # 4. Clean JSON output
            clean_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)
            clean_text = clean_text.replace("```json", "").replace("```", "").strip()

            try:
                parsed = json.loads(clean_text)
            except Exception:
                # Fallback: Find first {...} block
                match = re.search(r"\{.*\}", clean_text, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                else:
                    raise


            # 5. Extract and validate scores
            task_score = self._clamp_int(parsed.get("task_completion_score", 0), 0, 100)
            friction_score = self._clamp_int(parsed.get("friction_score", 1), 1, 5)
            tool_score = self._clamp_int(parsed.get("tool_accuracy_score", 100), 0, 100)

            mistakes = parsed.get("mistakes_detected", [])
            if not isinstance(mistakes, list):
                mistakes = [str(mistakes)] if mistakes else []

            lessons = parsed.get("actionable_lessons", [])
            if not isinstance(lessons, list):
                lessons = [str(lessons)] if lessons else []

            raw_extracted_facts = parsed.get("extracted_facts", {})
            if not isinstance(raw_extracted_facts, dict):
                raw_extracted_facts = {}

            # Sanitize extracted facts
            sanitized_facts = self.sanitizer.sanitize_dict(raw_extracted_facts)

            reasoning = parsed.get("reasoning", "")
            evaluation_details = {"reasoning": reasoning} if reasoning else {}

            result = {
                "session_id": session_id,
                "client_id": client_id,
                "domain_id": domain_id,
                "task_completion_score": task_score,
                "friction_score": friction_score,
                "tool_accuracy_score": tool_score,
                "evaluation_details": evaluation_details,
                "mistakes_detected": mistakes,
                "actionable_lessons": lessons,
                "extracted_facts": sanitized_facts,
            }

            logger.info(
                f"[EvaluatorJudge] Completed evaluation for {session_id} - "
                f"Task: {task_score}/100, Friction: {friction_score}/5, Tool Accuracy: {tool_score}/100, "
                f"Extracted Facts: {len(sanitized_facts)}"
            )
            return result

        except Exception as e:
            logger.error(f"[EvaluatorJudge] Evaluation failed for session {session_id}: {e}", exc_info=True)
            return fallback_evaluation

    @staticmethod
    def _clamp_int(val: Any, min_val: int, max_val: int) -> int:
        """Safely parse and clamp an integer within range."""
        try:
            num = int(float(val))
            return max(min_val, min(num, max_val))
        except (ValueError, TypeError):
            return min_val
