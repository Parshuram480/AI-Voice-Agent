"""Deterministic slot extraction for name and date of birth."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SlotFillResult:
    name: Optional[str] = None
    dob: Optional[str] = None
    dob_raw: Optional[str] = None
    dob_valid: bool = False


class SlotFiller:
    """Extract name and DOB slots from user text."""

    _name_patterns = [
        r"(?:my name is|i am|i'm|this is|call me)\s+([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,5})",
        r"(?:name is|name's)\s+([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,5})",
    ]

    _stopwords = {"and", "my", "dob", "date", "birth", "is", "was", "am", "i", "im", "born", "on"}
    _intent_noise = {"order", "status", "delivery", "shipping", "track", "package", "shipped"}

    _month_name = (
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    )

    _dob_patterns = [
        r"born\s+(?:on\s+)?(\w+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
        rf"born\s+(?:on\s+)?(\d{{1,2}}(?:st|nd|rd|th)?\s+{_month_name}\s+\d{{4}})",
        r"(?:date of birth|dob|d\.o\.b\.?)\s+(?:is\s+)?(\d{4}-\d{2}-\d{2})",
        r"(?:date of birth|dob|d\.o\.b\.?)\s+(?:is\s+)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        r"born\s+(?:on\s+)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
    ]

    _fallback_dob_patterns = [
        rf"\b(\d{{1,2}}(?:st|nd|rd|th)?\s+{_month_name}\s+\d{{4}})\b",
        rf"\b({_month_name}\s+\d{{1,2}}(?:st|nd|rd|th)?[,]?\s+\d{{4}})\b",
        r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\b",
        r"\b(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b",
    ]

    def extract(self, text: str) -> SlotFillResult:
        result = SlotFillResult()
        if not text:
            return result

        name = self._extract_name(text)
        if name:
            result.name = name

        dob_raw = self._extract_dob_raw(text)
        if dob_raw:
            result.dob_raw = dob_raw
            normalized = _parse_date_string(dob_raw)
            if normalized and _is_iso_date(normalized):
                result.dob = normalized
                result.dob_valid = True
            else:
                result.dob = normalized
                result.dob_valid = False

        return result

    def extract_name_candidate(self, text: str) -> Optional[str]:
        cleaned = re.sub(r"[^A-Za-z'\-\s]", "", text).strip()
        if not cleaned:
            return None

        parts = [p for p in cleaned.split() if p]
        if len(parts) < 2 or len(parts) > 5:
            return None
        if any(p.lower() in self._stopwords for p in parts):
            return None
        if any(p.lower() in self._intent_noise for p in parts):
            return None

        return " ".join(parts)

    def _extract_name(self, text: str) -> Optional[str]:
        for pattern in self._name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            raw = re.sub(r"[^A-Za-z'\-\s]", "", match.group(1))
            parts = [p for p in raw.split() if p]
            while parts and parts[-1].lower() in self._stopwords:
                parts.pop()

            cleaned = " ".join(parts).strip()
            if cleaned:
                return cleaned

        return None

    def _extract_dob_raw(self, text: str) -> Optional[str]:
        for pattern in self._dob_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        for pattern in self._fallback_dob_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None


def _is_iso_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _parse_date_string(date_str: str) -> str:
    date_str = date_str.strip().rstrip(",")
    date_str = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", date_str, flags=re.IGNORECASE)

    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    for fmt in ("%d %B %Y", "%d %B, %Y", "%d %b %Y", "%d %b, %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    match = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", date_str)
    if match:
        month, day, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    match = re.match(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", date_str)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    return date_str
