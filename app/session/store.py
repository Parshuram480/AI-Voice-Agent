"""Session storage abstractions."""

from abc import ABC, abstractmethod
from typing import Optional

from app.models.session import SessionState


class SessionStore(ABC):
    """Abstract session store for future Redis migration."""

    @abstractmethod
    def get(self, session_id: str) -> Optional[SessionState]:
        raise NotImplementedError

    @abstractmethod
    def set(self, session: SessionState) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def all_sessions(self) -> list[SessionState]:
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    """In-memory session storage for low-latency access."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    def set(self, session: SessionState) -> None:
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def all_sessions(self) -> list[SessionState]:
        return list(self._sessions.values())
