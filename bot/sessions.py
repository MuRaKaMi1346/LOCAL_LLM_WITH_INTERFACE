from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config import settings


@dataclass
class ConversationSession:
    user_id: str
    history: deque = field(default_factory=lambda: deque(maxlen=settings.max_history_turns * 2))
    last_active: datetime = field(default_factory=datetime.now)
    message_count: int = 0

    def add_user(self, text: str):
        self.history.append({"role": "user", "content": text})
        self.last_active = datetime.now()
        self.message_count += 1

    def add_assistant(self, text: str):
        self.history.append({"role": "assistant", "content": text})
        self.last_active = datetime.now()

    def get_messages(self) -> list[dict]:
        return list(self.history)

    def clear(self):
        self.history.clear()


class ConversationManager:
    def __init__(self, session_ttl_minutes: int = 60):
        self._sessions: dict[str, ConversationSession] = {}
        self._ttl = timedelta(minutes=session_ttl_minutes)

    def get_or_create(self, user_id: str) -> ConversationSession:
        self._evict_expired()
        if user_id not in self._sessions:
            self._sessions[user_id] = ConversationSession(user_id=user_id)
        return self._sessions[user_id]

    def clear(self, user_id: str):
        if user_id in self._sessions:
            self._sessions[user_id].clear()

    def clear_all(self):
        self._sessions.clear()

    def _evict_expired(self):
        now = datetime.now()
        expired = [uid for uid, s in self._sessions.items() if now - s.last_active > self._ttl]
        for uid in expired:
            del self._sessions[uid]

    def get_all_info(self) -> list[dict]:
        self._evict_expired()
        return [
            {
                "user_id": uid,
                "display_id": uid[:8] + "...",
                "msg_count": s.message_count,
                "last_active": s.last_active.strftime("%H:%M:%S"),
            }
            for uid, s in self._sessions.items()
        ]

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)


conversation_manager = ConversationManager()
