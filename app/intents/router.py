"""Deterministic intent router."""

import re

from app.models.intent import IntentResult


class IntentRouter:
    """Rule-based intent classification using keywords and regex."""

    def __init__(self) -> None:
        self._rules: list[tuple[str, list[str], list[re.Pattern[str]]]] = [
            (
                "greeting",
                [
                    "hello",
                    "hi",
                    "hey",
                    "hey there",
                    "hiya",
                    "good morning",
                    "good afternoon",
                    "good evening",
                    "good day",
                    "greetings",
                ],
                [
                    re.compile(r"\b(hi|hello|hey|hiya|greetings)\b", re.IGNORECASE),
                    re.compile(r"\bgood\s+(morning|afternoon|evening|day)\b", re.IGNORECASE),
                ],
            ),
            (
                "goodbye",
                [
                    "bye",
                    "goodbye",
                    "see you",
                    "thanks, bye",
                    "thank you, bye",
                    "that is all",
                    "that's all",
                    "nothing else",
                    "end call",
                ],
                [
                    re.compile(r"\b(bye|goodbye|see you)\b", re.IGNORECASE),
                    re.compile(r"\bthat(?:'s)?\s+all\b", re.IGNORECASE),
                    re.compile(r"\bnothing\s+else\b", re.IGNORECASE),
                    re.compile(r"\bthanks.*bye\b", re.IGNORECASE),
                ],
            ),
            (
                "help",
                [
                    "help",
                    "support",
                    "assist",
                    "what can you do",
                    "what can you help with",
                    "what are my options",
                    "need help",
                ],
                [
                    re.compile(r"\b(help|support|assist)\b", re.IGNORECASE),
                    re.compile(r"\bwhat\s+can\s+you\s+do\b", re.IGNORECASE),
                    re.compile(r"\bwhat\s+can\s+you\s+help\s+with\b", re.IGNORECASE),
                ],
            ),
            (
                "repeat_response",
                [
                    "repeat",
                    "repeat that",
                    "say that again",
                    "say it again",
                    "can you repeat",
                    "one more time",
                    "pardon",
                ],
                [
                    re.compile(r"\b(repeat|pardon)\b", re.IGNORECASE),
                    re.compile(r"\b(one\s+more\s+time|say\s+that\s+again|say\s+it\s+again)\b", re.IGNORECASE),
                ],
            ),
            (
                "delivery_date",
                [
                    "delivery date",
                    "arrival date",
                    "expected arrival",
                    "when will it arrive",
                    "when does it arrive",
                    "when will my order arrive",
                    "when is delivery",
                    "delivery time",
                    "eta",
                    "what is the eta",
                ],
                [
                    re.compile(r"\b(eta|arrival\s+date|expected\s+arrival|delivery\s+date)\b", re.IGNORECASE),
                    re.compile(r"\bwhen\s+(will|does)\s+.*\b(arrive|delivery)\b", re.IGNORECASE),
                ],
            ),
            (
                "order_status",
                [
                    "order status",
                    "order update",
                    "where is my order",
                    "where is my package",
                    "track my order",
                    "track order",
                    "tracking",
                    "shipping status",
                    "delivery status",
                    "has my order shipped",
                    "package status",
                ],
                [
                    re.compile(r"\b(order\s+status|shipping\s+status|delivery\s+status)\b", re.IGNORECASE),
                    re.compile(r"\btrack(ing)?\b", re.IGNORECASE),
                    re.compile(r"\bwhere\s+is\s+my\s+(order|package)\b", re.IGNORECASE),
                    re.compile(r"\bhas\s+my\s+order\s+shipped\b", re.IGNORECASE),
                ],
            ),
        ]

    def route(self, text: str) -> IntentResult:
        cleaned = (text or "").strip()
        if not cleaned:
            return IntentResult(intent="unsupported", confidence=0.0, reason="empty")

        lowered = cleaned.lower()
        for intent, keywords, patterns in self._rules:
            if any(kw in lowered for kw in keywords):
                return IntentResult(intent=intent, confidence=0.9, reason="keyword")
            if any(pattern.search(cleaned) for pattern in patterns):
                return IntentResult(intent=intent, confidence=0.9, reason="regex")

        return IntentResult(intent="unsupported", confidence=0.2, reason="no_match")
