import os
import re

# --- Environment Variables ---
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "900"))

"""Session manager with TTL and history trimming."""

import asyncio
from datetime import datetime, timedelta, UTC
from typing import Optional

from app.models.session import SessionState
from app.session.store import SessionStore
from app.state_machine.state_machine import ConversationState


class SessionManager:
    """Manages lifecycle of per-call sessions."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str) -> SessionState:
        async with self._lock:
            session = self._store.get(session_id)
            if session and not self._is_expired(session):
                return session

            session = SessionState(
                session_id=session_id,
                current_state=ConversationState.WAITING_FOR_INTENT.value,
            )
            self._store.set(session)
            return session

    async def update(self, session: SessionState) -> None:
        async with self._lock:
            session.touch()
            self._store.set(session)

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._store.delete(session_id)

    async def cleanup(self) -> int:
        async with self._lock:
            expired = [s.session_id for s in self._store.all_sessions() if self._is_expired(s)]
            for session_id in expired:
                self._store.delete(session_id)
            return len(expired)

    def _is_expired(self, session: SessionState) -> bool:
        ttl = timedelta(seconds=SESSION_TTL_SECONDS)
        return datetime.now(UTC) - session.updated_at > ttl
