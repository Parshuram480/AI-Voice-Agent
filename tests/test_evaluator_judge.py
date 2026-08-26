"""Unit tests for EvaluatorJudge and post-call continuous learning flywheel."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.memory.evaluator_judge import EvaluatorJudge
from app.memory.memory_manager import MemoryManager
from app.memory.pii_sanitizer import PIISanitizer


@pytest.fixture
def mock_groq_client():
    client = MagicMock()
    client.chat_completion = AsyncMock()
    return client


@pytest.fixture
def mock_system_db():
    db = MagicMock()
    db.save_call_evaluation = AsyncMock(return_value=True)
    db.get_caller_profile = AsyncMock(return_value=None)
    db.upsert_caller_profile = AsyncMock(return_value={"id": 1, "profile_data": {}})
    db.upsert_learned_rule = AsyncMock(return_value={"id": 1})
    return db


@pytest.mark.asyncio
async def test_evaluator_judge_success(mock_groq_client):
    judge_response = {
        "task_completion_score": 95,
        "friction_score": 1,
        "tool_accuracy_score": 100,
        "reasoning": "The agent verified the caller smoothly and retrieved order status without issues.",
        "mistakes_detected": [],
        "actionable_lessons": ["Confirm delivery preference on weekend calls"],
        "extracted_facts": {
            "preferred_name": "Sarah Connor",
            "delivery_window": "After 5 PM"
        }
    }
    mock_groq_client.chat_completion.return_value = json.dumps(judge_response)

    judge = EvaluatorJudge(groq_client=mock_groq_client)
    history = [
        {"role": "assistant", "content": "Hello, how can I help you today?"},
        {"role": "user", "content": "Hi, my name is Sarah Connor. Please deliver my order after 5 PM."}
    ]

    result = await judge.evaluate_call(
        session_id="sess_123",
        history=history,
        domain="food",
        client_id=1,
        domain_id=2,
        caller_identifier="+15551234567"
    )

    assert result["session_id"] == "sess_123"
    assert result["task_completion_score"] == 95
    assert result["friction_score"] == 1
    assert result["tool_accuracy_score"] == 100
    assert result["extracted_facts"]["preferred_name"] == "Sarah Connor"
    assert result["extracted_facts"]["delivery_window"] == "After 5 PM"
    assert len(result["actionable_lessons"]) == 1


@pytest.mark.asyncio
async def test_evaluator_judge_pii_redaction(mock_groq_client):
    # LLM returns facts that might have contained sensitive data
    judge_response = {
        "task_completion_score": 80,
        "friction_score": 2,
        "tool_accuracy_score": 90,
        "reasoning": "Caller provided card 4532 0150 1234 5674 for billing.",
        "mistakes_detected": [],
        "actionable_lessons": [],
        "extracted_facts": {
            "payment_note": "Card 4532 0150 1234 5674 verified"
        }
    }
    mock_groq_client.chat_completion.return_value = json.dumps(judge_response)

    judge = EvaluatorJudge(groq_client=mock_groq_client)
    history = [
        {"role": "user", "content": "My credit card is 4532 0150 1234 5674 and SSN is 123-45-6789."}
    ]

    result = await judge.evaluate_call(
        session_id="sess_pii",
        history=history,
        caller_identifier="+15559998888"
    )

    # Verify extracted facts are sanitized
    assert "[REDACTED_CREDIT_CARD]" in result["extracted_facts"]["payment_note"]
    assert "4532 0150 1234 5674" not in result["extracted_facts"]["payment_note"]

    # Verify input transcript sent to LLM was also sanitized
    call_args = mock_groq_client.chat_completion.call_args[1]
    user_prompt = call_args["messages"][1]["content"]
    assert "4532 0150 1234 5674" not in user_prompt
    assert "[REDACTED_CREDIT_CARD]" in user_prompt
    assert "[REDACTED_SSN]" in user_prompt


@pytest.mark.asyncio
async def test_evaluator_judge_empty_history(mock_groq_client):
    judge = EvaluatorJudge(groq_client=mock_groq_client)
    result = await judge.evaluate_call(session_id="sess_empty", history=[])

    assert result["session_id"] == "sess_empty"
    assert result["task_completion_score"] == 0
    assert result["friction_score"] == 1
    assert result["extracted_facts"] == {}
    mock_groq_client.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_evaluator_judge_llm_exception_fallback(mock_groq_client):
    mock_groq_client.chat_completion.side_effect = Exception("API rate limit exceeded")

    judge = EvaluatorJudge(groq_client=mock_groq_client)
    history = [{"role": "user", "content": "Hello"}]

    result = await judge.evaluate_call(session_id="sess_err", history=history)

    assert result["session_id"] == "sess_err"
    assert result["task_completion_score"] == 0
    assert result["extracted_facts"] == {}


@pytest.mark.asyncio
async def test_process_post_call_learning_flow(mock_system_db, mock_groq_client):
    judge_response = {
        "task_completion_score": 90,
        "friction_score": 1,
        "tool_accuracy_score": 100,
        "reasoning": "High quality interaction.",
        "mistakes_detected": [],
        "actionable_lessons": ["Greet caller by name when profile exists"],
        "extracted_facts": {
            "doctor_preference": "Dr. House"
        }
    }
    mock_groq_client.chat_completion.return_value = json.dumps(judge_response)

    judge = EvaluatorJudge(groq_client=mock_groq_client)
    manager = MemoryManager(system_db=mock_system_db)

    history = [
        {"role": "user", "content": "I prefer Dr. House for my appointments."}
    ]

    result = await manager.process_post_call_learning(
        session_id="sess_flywheel",
        history=history,
        domain="healthcare",
        client_id=1,
        domain_id=2,
        caller_identifier="+15554443333",
        evaluator_judge=judge
    )

    assert result["evaluation"] is not None
    assert result["evaluation"]["task_completion_score"] == 90
    mock_system_db.save_call_evaluation.assert_called_once()
    mock_system_db.upsert_caller_profile.assert_called_once()
