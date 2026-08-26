"""Tests for PII and Sensitive Data Sanitizer."""

import time
import pytest
from app.memory.pii_sanitizer import PIISanitizer, sanitize_text, sanitize_transcript, sanitize_dict


def test_sanitize_credit_card():
    # Valid Visa card format (passes Luhn)
    sample = "My card number is 4532 0150 1234 5674 please charge it."
    result = sanitize_text(sample)
    assert "[REDACTED_CREDIT_CARD]" in result
    assert "4532 0150 1234 5674" not in result

    # Standard phone numbers should not be redacted as credit card
    phone_sample = "Call me at +1 555-234-5678 tomorrow."
    assert "555-234-5678" in sanitize_text(phone_sample)


def test_sanitize_ssn():
    sample = "My SSN is 123-45-6789 and my name is Alex."
    result = sanitize_text(sample)
    assert "[REDACTED_SSN]" in result
    assert "123-45-6789" not in result


def test_sanitize_cvv_and_pin():
    sample = "Security code is cvv: 894 and my pin is 4492."
    result = sanitize_text(sample)
    assert "[REDACTED_CVV]" in result
    assert "[REDACTED_PIN]" in result
    assert "894" not in result
    assert "4492" not in result


def test_sanitize_passwords_and_api_keys():
    sample = "My password: SuperSecret123! and API key is gsk_abcdef1234567890abcdef1234567890"
    result = sanitize_text(sample)
    assert "[REDACTED_PASSWORD]" in result
    assert "[REDACTED_API_KEY]" in result
    assert "SuperSecret123!" not in result
    assert "gsk_abcdef1234567890abcdef1234567890" not in result


def test_sanitize_transcript():
    transcript = [
        {"role": "user", "content": "Hi, my SSN is 987-65-4321."},
        {"role": "assistant", "content": "Thank you, verification passed."},
        {"role": "user", "content": "My pin: 1234 for authorization."}
    ]
    cleaned = sanitize_transcript(transcript)
    assert len(cleaned) == 3
    assert "[REDACTED_SSN]" in cleaned[0]["content"]
    assert "[REDACTED_PIN]" in cleaned[2]["content"]
    assert "987-65-4321" not in cleaned[0]["content"]


def test_sanitize_dict():
    nested_data = {
        "user": "John Doe",
        "billing": {
            "card": "4532015012345674",
            "cvv": "cvv 123"
        },
        "notes": ["Secret password: MyPassword99!", "Harmless note"]
    }
    cleaned = sanitize_dict(nested_data)
    assert "[REDACTED_CREDIT_CARD]" in cleaned["billing"]["card"]
    assert "[REDACTED_CVV]" in cleaned["billing"]["cvv"]
    assert "[REDACTED_PASSWORD]" in cleaned["notes"][0]
    assert cleaned["notes"][1] == "Harmless note"


def test_sanitizer_speed_benchmark():
    long_text = "Call Alex at 555-123-4567. SSN is 000-11-2222. Paid with card 4532 0150 1234 5674 and cvv 432. Password: TopSecret! " * 20
    start = time.perf_counter()
    sanitized = sanitize_text(long_text)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    # Must complete fast (< 5ms for large payload)
    assert elapsed_ms < 10.0
    assert "[REDACTED_SSN]" in sanitized
    assert "[REDACTED_CREDIT_CARD]" in sanitized
