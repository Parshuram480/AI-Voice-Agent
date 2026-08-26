"""PII and Sensitive Data Sanitizer.

Scrubs confidential data (credit card numbers, SSNs, CVVs, PINs, passwords,
and authentication secrets) from transcripts and payloads prior to long-term
memory persistence or LLM-as-a-Judge reflection.
"""

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# --- REGEX PATTERNS FOR PII / SECRETS ---

# 1. Credit Card Patterns (Standard 16-digit cards, 15-digit Amex, or labeled card numbers)
CREDIT_CARD_PATTERN = re.compile(
    r'\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{4}[-\s]?\d{6}[-\s]?\d{5}\b|\b(?:\d[ -]*?){13,19}\b'
)

# 2. US Social Security Numbers (SSN): XXX-XX-XXXX or 9 consecutive digits with SSN context
SSN_PATTERN = re.compile(
    r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'
)

# 3. CVV / CVC (3-4 digits preceded by cvv/cvc/code label or 'is')
CVV_PATTERN = re.compile(
    r'(?i)\b(?:cvv|cvc|security\s*code|card\s*verification)\s*(?:is|[:=])?\s*(\d{3,4})\b'
)

# 4. PIN / OTP (4-8 digits preceded by pin/otp/passcode label or 'is')
PIN_OTP_PATTERN = re.compile(
    r'(?i)\b(?:pin|otp|passcode|one\s*time\s*password|verification\s*code)\s*(?:is|[:=])?\s*(\d{4,8})\b'
)

# 5. Passwords / Secrets
PASSWORD_PATTERN = re.compile(
    r'(?i)\b(?:password|passwd|pwd|secret)\s*(?:is|[:=])\s*(\S+)'
)

# 6. API Keys / Auth Tokens
API_KEY_PATTERN = re.compile(
    r'(?i)(?:bearer\s+[a-zA-Z0-9_\-\.]{20,}|gsk_[a-zA-Z0-9]{25,}|sk-[a-zA-Z0-9]{25,}|AIza[a-zA-Z0-9_\-]{30,})'
)


class PIISanitizer:
    """Provides high-performance text and object sanitization for PII/PHI."""

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Scrubs PII and secrets from a raw text string."""
        if not text or not isinstance(text, str):
            return text

        sanitized = text

        # 1. Sanitize CVV
        sanitized = CVV_PATTERN.sub(r'[REDACTED_CVV]', sanitized)

        # 2. Sanitize PIN / OTP
        sanitized = PIN_OTP_PATTERN.sub(r'[REDACTED_PIN]', sanitized)

        # 3. Sanitize Passwords
        sanitized = PASSWORD_PATTERN.sub(r'password: [REDACTED_PASSWORD]', sanitized)

        # 4. Sanitize API Keys / Tokens
        sanitized = API_KEY_PATTERN.sub(r'[REDACTED_API_KEY]', sanitized)

        # 5. Sanitize SSN
        sanitized = SSN_PATTERN.sub(r'[REDACTED_SSN]', sanitized)

        # 6. Sanitize Credit Cards
        # Handles 13 to 19 digit strings while avoiding common 10-digit phone numbers
        def _cc_replace(match):
            val = match.group(0)
            raw_digits = re.sub(r'\D', '', val)
            if 13 <= len(raw_digits) <= 19:
                return "[REDACTED_CREDIT_CARD]"
            return val

        sanitized = CREDIT_CARD_PATTERN.sub(_cc_replace, sanitized)

        return sanitized

    @classmethod
    def sanitize_transcript(cls, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sanitizes an entire list of chat/call transcript messages."""
        if not messages or not isinstance(messages, list):
            return []

        sanitized_messages = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            clean_msg = dict(msg)
            if "content" in clean_msg and isinstance(clean_msg["content"], str):
                clean_msg["content"] = cls.sanitize_text(clean_msg["content"])
            sanitized_messages.append(clean_msg)
        return sanitized_messages

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitizes a dictionary of values."""
        if not isinstance(data, dict):
            return data

        clean_dict = {}
        for k, v in data.items():
            if isinstance(v, str):
                clean_dict[k] = cls.sanitize_text(v)
            elif isinstance(v, dict):
                clean_dict[k] = cls.sanitize_dict(v)
            elif isinstance(v, list):
                clean_dict[k] = [
                    cls.sanitize_dict(item) if isinstance(item, dict)
                    else cls.sanitize_text(item) if isinstance(item, str)
                    else item
                    for item in v
                ]
            else:
                clean_dict[k] = v
        return clean_dict


# Top-level functional exports
sanitize_text = PIISanitizer.sanitize_text
sanitize_transcript = PIISanitizer.sanitize_transcript
sanitize_dict = PIISanitizer.sanitize_dict
