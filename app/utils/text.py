"""Text normalization helpers."""

import re


def normalize_text(text: str) -> str:
    """Normalize whitespace and lowercase for matching."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned
