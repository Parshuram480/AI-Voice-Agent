"""Semantic Memory Manager.

Manages persistent caller profile memory, fact storage, entity reconciliation,
and compact prompt formatting for real-time voice injection.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.system_database import SystemDatabase
from app.memory.pii_sanitizer import PIISanitizer

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages semantic caller memory and lifecycle across calls."""

    def __init__(self, system_db: Optional[SystemDatabase] = None):
        self.system_db = system_db or SystemDatabase()
        self.sanitizer = PIISanitizer()

    async def get_caller_memory(
        self,
        client_id: int,
        domain_id: Optional[int],
        caller_identifier: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves caller semantic profile for a given identifier (phone or verified ID).
        """
        if not caller_identifier or not str(caller_identifier).strip():
            return None

        try:
            profile_row = await self.system_db.get_caller_profile(
                client_id=client_id,
                domain_id=domain_id,
                caller_identifier=str(caller_identifier).strip()
            )
            return profile_row
        except Exception as e:
            logger.error(f"Error fetching caller memory for {caller_identifier}: {e}")
            return None

    async def upsert_caller_memory(
        self,
        client_id: int,
        domain_id: Optional[int],
        caller_identifier: str,
        new_facts: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Reconciles and updates caller facts into persistent storage.
        All facts are sanitized of PII before saving.
        """
        if not caller_identifier or not str(caller_identifier).strip() or not new_facts:
            return None

        clean_identifier = str(caller_identifier).strip()

        try:
            # 1. Fetch existing profile
            existing_record = await self.get_caller_memory(
                client_id=client_id,
                domain_id=domain_id,
                caller_identifier=clean_identifier
            )
            existing_profile_data = existing_record.get("profile_data", {}) if existing_record else {}

            # 2. Sanitize incoming new facts
            sanitized_new_facts = self.sanitizer.sanitize_dict(new_facts)

            # 3. Normalize semantic keys and merge facts
            def _normalize_key(k: str, v: Any) -> str:
                k_low = k.lower().strip()
                v_str = str(v).lower()
                if k_low in ("customer_name", "preferred_name"):
                    return k_low
                if "name" in k_low:
                    return "customer_name"
                if "allergy" in k_low or "allergies" in k_low:
                    return "allergies"


                if any(term in k_low for term in ("comm", "whatsapp", "sms", "email", "notification", "remind")):
                    return "communication_preference"
                if any(term in k_low for term in ("format", "mode", "video", "in_person", "consultation")):
                    return "consultation_format"
                if any(term in k_low for term in ("time", "schedule", "appointment", "hour", "day")):
                    return "preferred_time"
                if any(term in v_str for term in ("afternoon", "morning", "evening", "pm", "am", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")):
                    return "preferred_time"
                if any(term in v_str for term in ("video call", "in-person", "telehealth")):
                    return "consultation_format"
                return k_low

            merged_data = dict(existing_profile_data)
            now_iso = datetime.now(timezone.utc).isoformat()

            for raw_key, value in sanitized_new_facts.items():
                if value is None or str(value).strip() == "":
                    continue

                canonical_key = _normalize_key(raw_key, value)
                
                # If updating preferred_time or consultation_format, remove generic legacy keys
                if canonical_key in ("preferred_time", "consultation_format"):
                    merged_data.pop("preference_key", None)
                    merged_data.pop("preferred_schedule", None)
                
                # If value is a structured dict with confidence or timestamp
                if isinstance(value, dict) and "value" in value:
                    merged_data[canonical_key] = {
                        "value": value["value"],
                        "confidence": value.get("confidence", 1.0),
                        "updated_at": now_iso
                    }
                else:
                    # Flat key-value pair
                    merged_data[canonical_key] = {
                        "value": value,
                        "confidence": 1.0,
                        "updated_at": now_iso
                    }

            # 4. Save to PostgreSQL
            updated_row = await self.system_db.upsert_caller_profile(
                client_id=client_id,
                domain_id=domain_id,
                caller_identifier=clean_identifier,
                profile_data=merged_data
            )
            return updated_row
        except Exception as e:
            logger.error(f"Error upserting caller memory for {caller_identifier}: {e}")
            return None

    @staticmethod
    def format_memory_for_prompt(profile_data: Optional[Dict[str, Any]]) -> str:
        """
        Converts caller profile facts into a concise markdown context block
        for zero-latency injection into system prompts (< 80 tokens).
        """
        if not profile_data or not isinstance(profile_data, dict):
            return ""

        facts_lines: List[str] = []
        for key, entry in profile_data.items():
            # Skip internal metadata keys
            if key.startswith("_"):
                continue

            # Handle both dictionary entries with 'value' and flat values
            if isinstance(entry, dict) and "value" in entry:
                val = entry["value"]
            else:
                val = entry

            if val is not None and str(val).strip():
                # Format key for human readability (e.g., 'preferred_delivery_time' -> 'Preferred Delivery Time')
                clean_key = key.replace("_", " ").title()
                facts_lines.append(f"- {clean_key}: {val}")

        if not facts_lines:
            return ""

        joined_facts = "\n".join(facts_lines)
        return f"\n<caller_profile>\n# KNOWN CALLER CONTEXT & PREFERENCES (FROM PAST CALLS)\n{joined_facts}\n</caller_profile>"

    async def process_post_call_learning(
        self,
        session_id: str,
        history: List[Dict[str, Any]],
        domain: Optional[str] = None,
        client_id: Optional[int] = None,
        domain_id: Optional[int] = None,
        caller_identifier: Optional[str] = None,
        evaluator_judge: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Post-call orchestration flywheel:
        1. Runs LLM-as-a-Judge post-call quality evaluation.
        2. Saves evaluation scores, friction, and mistakes to PostgreSQL `call_evaluations`.
        3. If new facts are extracted and caller_identifier is present, reconciles and updates `caller_profiles`.
        4. If high-confidence actionable lessons are found, saves them into `domain_learned_rules`.
        """
        from app.memory.evaluator_judge import EvaluatorJudge

        judge = evaluator_judge or EvaluatorJudge(sanitizer=self.sanitizer)

        try:
            # 1. Run LLM evaluation
            evaluation = await judge.evaluate_call(
                session_id=session_id,
                history=history,
                domain=domain,
                client_id=client_id,
                domain_id=domain_id,
                caller_identifier=caller_identifier,
            )

            # 2. Persist call evaluation in PostgreSQL
            try:
                await self.system_db.save_call_evaluation(evaluation)
            except Exception as eval_err:
                logger.warning(f"Failed to persist call evaluation for session {session_id}: {eval_err}")

            # 3. Reconcile & Persist extracted caller facts if available
            extracted_facts = evaluation.get("extracted_facts", {})
            updated_profile = None
            if extracted_facts and client_id is not None and caller_identifier:
                updated_profile = await self.upsert_caller_memory(
                    client_id=client_id,
                    domain_id=domain_id,
                    caller_identifier=caller_identifier,
                    new_facts=extracted_facts,
                )


            # 4. Optional: Save actionable lessons as domain learned rules
            actionable_lessons = evaluation.get("actionable_lessons", [])
            for lesson in actionable_lessons:
                if isinstance(lesson, str) and len(lesson.strip()) > 10:
                    try:
                        await self.system_db.upsert_learned_rule(
                            client_id=client_id,
                            domain_id=domain_id,
                            rule_category="call_evaluation",
                            trigger_condition=f"General interactions in {domain or 'domain'}",
                            instruction=lesson.strip(),
                            confidence_score=0.85,
                            status="active",
                        )
                    except Exception as rule_err:
                        logger.warning(f"Could not persist learned rule from lesson '{lesson}': {rule_err}")

            return {
                "evaluation": evaluation,
                "caller_profile": updated_profile,
            }

        except Exception as e:
            logger.error(f"Post-call learning failed for session {session_id}: {e}", exc_info=True)
            return {
                "evaluation": None,
                "caller_profile": None,
                "error": str(e),
            }

