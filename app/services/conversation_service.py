"""Deterministic conversation orchestration service."""
from __future__ import annotations

import os
import re

# --- Environment Variables ---
SESSION_MAX_RETRIES = int(os.getenv("SESSION_MAX_RETRIES", "2"))
SESSION_MAX_TURNS = int(os.getenv("SESSION_MAX_TURNS", "10"))

import time
from typing import Optional

from app.intents import IntentRouter, SlotFiller, SlotFillResult
from app.logging.logger import log_event
from app.models.response import ConversationResult
from app.models.session import SessionState
from app.observability.metrics import LatencyTracker
from app.services.order_service import OrderService
from app.services.verification_service import VerificationService
from app.session.manager import SessionManager
from app.state_machine.state_machine import ConversationState, ConversationStateMachine
from app.utils.text import normalize_text


class ConversationService:
    """Primary orchestration layer for deterministic dialog."""

    def __init__(
        self,
        session_manager: SessionManager,
        intent_router: IntentRouter,
        slot_filler: SlotFiller,
        state_machine: ConversationStateMachine,
        verification_service: VerificationService,
        order_service: OrderService,
    ) -> None:
        self._sessions = session_manager
        self._intents = intent_router
        self._slots = slot_filler
        self._state_machine = state_machine
        self._verification = verification_service
        self._orders = order_service

    async def handle_user_text(self, session_id: str, user_text: str) -> ConversationResult:
        timings: dict[str, float] = {}
        tracker = LatencyTracker(timings)
        t0 = time.perf_counter()

        session = await self._sessions.get_or_create(session_id)
        cleaned = normalize_text(user_text)

        if not cleaned:
            reply = "I'm sorry, I didn't catch that. Please repeat."
            next_state = self._safe_state(session, ConversationState.WAITING_FOR_INTENT)
            result = self._finalize(session, reply, next_state, intent="unsupported", user_text=cleaned)
            await self._sessions.update(session)
            result.timings["total"] = round(time.perf_counter() - t0, 4)
            return result

        slot_result = self._slots.extract(cleaned)
        if session.current_state == ConversationState.WAITING_FOR_NAME.value and not slot_result.name:
            candidate = self._slots.extract_name_candidate(cleaned)
            if candidate:
                slot_result.name = candidate
        self._apply_slots(session, slot_result)

        intent = self._resolve_intent(session, cleaned)
        session.current_intent = intent

        reply_text = ""
        next_state = ConversationState.WAITING_FOR_INTENT
        should_end = False
        customer: Optional[dict] = None
        orders: list[dict] = []

        if intent == "goodbye":
            reply_text = "Thanks for calling. Goodbye."
            next_state = ConversationState.END_CALL
            should_end = True
        elif intent == "help":
            reply_text = "I can help with order status or delivery dates. What would you like to check?"
            next_state = ConversationState.WAITING_FOR_INTENT
        elif intent == "repeat_response":
            reply_text = session.last_response or "I don't have anything to repeat yet. How can I help?"
            next_state = ConversationState.WAITING_FOR_INTENT
        elif intent == "greeting":
            reply_text = "Hello, how may I help you today?"
            next_state = ConversationState.WAITING_FOR_INTENT
        elif intent in {"order_status", "delivery_date"}:
            reply_text, next_state, should_end, customer, orders = await self._handle_order_intent(
                session,
                intent,
                slot_result,
                tracker,
            )
        else:
            reply_text = (
                "I'm sorry, I'm not able to help with that yet. "
                "Please ask about your orders or delivery status."
            )
            next_state = ConversationState.FALLBACK

        transition = self._state_machine.transition(session, next_state)
        if not transition.allowed:
            reply_text = (
                "I'm sorry, I'm not able to help with that yet. "
                "Please ask about your orders or delivery status."
            )
            next_state = ConversationState.FALLBACK
            should_end = False

        result = self._finalize(
            session,
            reply_text,
            next_state,
            intent=intent,
            should_end=should_end,
            user_text=cleaned,
        )
        result.customer = customer
        result.orders = orders
        result.timings.update(timings)
        result.timings["total"] = round(time.perf_counter() - t0, 4)

        await self._sessions.update(session)

        log_event(
            "conversation_turn",
            session_id=session.session_id,
            intent=intent,
            state=result.state,
            verified=session.verified,
            retries=session.retry_counts,
        )

        return result

    def _resolve_intent(self, session: SessionState, cleaned_text: str) -> str:
        if session.current_state in {
            ConversationState.WAITING_FOR_NAME.value,
            ConversationState.WAITING_FOR_DOB.value,
            ConversationState.VERIFYING_USER.value,
        }:
            if session.current_intent in {"order_status", "delivery_date"}:
                return session.current_intent

        intent_result = self._intents.route(cleaned_text)
        return intent_result.intent

    def _apply_slots(self, session: SessionState, slot_result: SlotFillResult) -> None:
        if slot_result.name:
            session.user_name = slot_result.name
        if slot_result.dob_valid:
            session.dob = slot_result.dob

    async def _handle_order_intent(
        self,
        session: SessionState,
        intent: str,
        slot_result: SlotFillResult,
        tracker: LatencyTracker,
    ) -> tuple[str, ConversationState, bool, Optional[dict], list[dict]]:
        customer: Optional[dict] = None
        orders: list[dict] = []

        if not session.user_name:
            return self._prompt_for_slot(session, "name")

        if not session.dob:
            if slot_result.dob_raw and not slot_result.dob_valid:
                return self._prompt_for_slot(session, "dob_invalid")
            return self._prompt_for_slot(session, "dob")

        if not session.verified:
            with tracker.track("verification"):
                verification = await self._verification.verify(session.user_name, session.dob)
            if not verification.verified:
                return self._handle_verification_failure(session)

            customer = verification.customer
            session.verified = True
            if customer:
                session.customer_id = customer.get("id")

        if session.customer_id:
            with tracker.track("db_lookup"):
                orders_res = await self._orders.get_orders(session.customer_id)
                if isinstance(orders_res, dict):
                    orders = orders_res.get("recent_orders", [])
                else:
                    orders = orders_res
            if orders:
                session.last_order = orders[0]

        reply_text = self._build_order_response(intent, session, orders)
        reply_text = f"Thank you. Let me check your order. {reply_text}"
        reply_text = f"{reply_text} Is there anything else I can help you with?"
        return reply_text, ConversationState.FOLLOWUP, False, customer, orders

    def _prompt_for_slot(self, session: SessionState, slot: str) -> tuple[str, ConversationState, bool, None, list[dict]]:
        if slot == "name":
            self._bump_retry(session, "name")
            if self._retry_exhausted(session, "name"):
                return self._fallback_response()
            return "Sure. Please provide your full name.", ConversationState.WAITING_FOR_NAME, False, None, []

        if slot == "dob_invalid":
            self._bump_retry(session, "dob")
            if self._retry_exhausted(session, "dob"):
                return self._fallback_response()
            return (
                "That date of birth doesn't look valid. Please say it as YYYY-MM-DD.",
                ConversationState.WAITING_FOR_DOB,
                False,
                None,
                [],
            )

        self._bump_retry(session, "dob")
        if self._retry_exhausted(session, "dob"):
            return self._fallback_response()
        return (
            "Please provide your date of birth in YYYY-MM-DD.",
            ConversationState.WAITING_FOR_DOB,
            False,
            None,
            [],
        )

    def _handle_verification_failure(self, session: SessionState) -> tuple[str, ConversationState, bool, None, list[dict]]:
        self._bump_retry(session, "verification")
        if self._retry_exhausted(session, "verification"):
            return self._fallback_response()
        session.verified = False
        session.customer_id = None
        session.last_order = None
        return (
            "I couldn't verify your account. Please repeat your full name and date of birth.",
            ConversationState.WAITING_FOR_NAME,
            False,
            None,
            [],
        )

    def _build_order_response(self, intent: str, session: SessionState, orders: list[dict]) -> str:
        if not orders:
            return "I found your account, but there are no recent orders on file."

        latest = orders[0]
        status = latest.get("status", "unknown")
        order_number = latest.get("order_number", "your order")
        eta = latest.get("estimated_arrival")

        if intent == "delivery_date":
            if eta:
                return f"Your order {order_number} is expected to arrive on {eta}."
            return f"Your order {order_number} does not have an estimated arrival date yet."

        if eta:
            return f"Your order {order_number} is {status} and is expected to arrive on {eta}."
        return f"Your order {order_number} is {status}."

    def _fallback_response(self) -> tuple[str, ConversationState, bool, None, list[dict]]:
        return (
            "I'm sorry, I'm not able to help with that yet. "
            "Please ask about your orders or delivery status.",
            ConversationState.FALLBACK,
            False,
            None,
            [],
        )

    def _safe_state(self, session: SessionState, next_state: ConversationState) -> ConversationState:
        transition = self._state_machine.transition(session, next_state)
        if transition.allowed:
            return next_state
        return ConversationState.FALLBACK

    def _bump_retry(self, session: SessionState, key: str) -> None:
        session.retry_counts[key] = session.retry_counts.get(key, 0) + 1

    def _retry_exhausted(self, session: SessionState, key: str) -> bool:
        return session.retry_counts.get(key, 0) > SESSION_MAX_RETRIES

    def _finalize(
        self,
        session: SessionState,
        reply_text: str,
        next_state: ConversationState,
        intent: str,
        should_end: bool = False,
        user_text: str = "",
    ) -> ConversationResult:
        session.current_state = next_state.value
        session.last_response = reply_text
        if user_text:
            session.add_turn("user", user_text, SESSION_MAX_TURNS)
        session.add_turn("assistant", reply_text, SESSION_MAX_TURNS)

        return ConversationResult(
            session_id=session.session_id,
            intent=intent,
            reply_text=reply_text,
            state=session.current_state,
            should_end=should_end,
            verified=session.verified,
            customer=None,
            orders=[],
            timings={},
        )
