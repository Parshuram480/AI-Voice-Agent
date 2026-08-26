"""Unit tests for MemoryManager."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.memory.memory_manager import MemoryManager


@pytest.fixture
def mock_system_db():
    db = MagicMock()
    db.get_caller_profile = AsyncMock()
    db.upsert_caller_profile = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_get_caller_memory(mock_system_db):
    mock_system_db.get_caller_profile.return_value = {
        "id": 1,
        "caller_identifier": "+15551234567",
        "profile_data": {
            "preferred_name": "Alex",
            "delivery_window": "After 5 PM"
        }
    }
    manager = MemoryManager(system_db=mock_system_db)
    memory = await manager.get_caller_memory(client_id=1, domain_id=2, caller_identifier="+15551234567")

    assert memory is not None
    assert memory["caller_identifier"] == "+15551234567"
    assert memory["profile_data"]["preferred_name"] == "Alex"
    mock_system_db.get_caller_profile.assert_called_once_with(
        client_id=1, domain_id=2, caller_identifier="+15551234567"
    )


@pytest.mark.asyncio
async def test_upsert_caller_memory_with_pii_sanitization(mock_system_db):
    mock_system_db.get_caller_profile.return_value = None
    mock_system_db.upsert_caller_profile.side_effect = lambda client_id, domain_id, caller_identifier, profile_data: {
        "client_id": client_id,
        "domain_id": domain_id,
        "caller_identifier": caller_identifier,
        "profile_data": profile_data
    }

    manager = MemoryManager(system_db=mock_system_db)
    new_facts = {
        "preferred_name": "John",
        "billing_note": "Card was 4532 0150 1234 5674 and ssn is 123-45-6789",
        "notes": "Prefers evening callbacks"
    }

    result = await manager.upsert_caller_memory(
        client_id=1,
        domain_id=2,
        caller_identifier="+15559876543",
        new_facts=new_facts
    )

    assert result is not None
    saved_profile = result["profile_data"]
    assert saved_profile["preferred_name"]["value"] == "John"
    assert "[REDACTED_CREDIT_CARD]" in saved_profile["billing_note"]["value"]
    assert "[REDACTED_SSN]" in saved_profile["billing_note"]["value"]
    assert "4532 0150 1234 5674" not in saved_profile["billing_note"]["value"]


def test_format_memory_for_prompt():
    profile_data = {
        "preferred_name": {"value": "Alex", "confidence": 1.0},
        "delivery_time": "After 5:00 PM",
        "language_preference": "English"
    }

    prompt_injection = MemoryManager.format_memory_for_prompt(profile_data)
    assert "<caller_profile>" in prompt_injection
    assert "- Preferred Name: Alex" in prompt_injection
    assert "- Delivery Time: After 5:00 PM" in prompt_injection
    assert "- Language Preference: English" in prompt_injection
    assert "</caller_profile>" in prompt_injection


def test_format_memory_for_empty_profile():
    assert MemoryManager.format_memory_for_prompt(None) == ""
    assert MemoryManager.format_memory_for_prompt({}) == ""
