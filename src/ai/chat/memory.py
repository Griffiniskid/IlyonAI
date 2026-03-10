"""
Conversation memory for the AI chat engine.

Stores per-session message history in-process (Redis-backed if available).
Each session is identified by a session_id (UUID assigned at chat start).
"""

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum messages to retain per session
MAX_MESSAGES_PER_SESSION = 40
# Session TTL in seconds (2 hours of inactivity)
SESSION_TTL = 7200
# Max concurrent in-memory sessions
MAX_SESSIONS = 500


@dataclass
class ChatMessage:
    role: str           # "user" | "assistant" | "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: Optional[List[Dict[str, Any]]] = None   # For assistant messages with tool use
    tool_call_id: Optional[str] = None                   # For tool result messages
    tool_name: Optional[str] = None

    def to_openai_dict(self) -> Dict[str, Any]:
        """Serialize to OpenAI-compatible message dict."""
        msg: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.tool_name and self.role == "tool":
            msg["name"] = self.tool_name
        return msg


@dataclass
class Session:
    session_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add(self, msg: ChatMessage):
        self.messages.append(msg)
        self.last_active = time.time()
        # Trim oldest messages if over limit (keep system context)
        if len(self.messages) > MAX_MESSAGES_PER_SESSION:
            self.messages = self.messages[-MAX_MESSAGES_PER_SESSION:]

    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > SESSION_TTL

    def to_openai_messages(self) -> List[Dict[str, Any]]:
        return [m.to_openai_dict() for m in self.messages]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "message_count": len(self.messages),
            "created_at": self.created_at,
            "last_active": self.last_active,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                }
                for m in self.messages
                if m.role in ("user", "assistant")
            ],
        }


class ConversationMemory:
    """
    In-process conversation memory with LRU eviction.

    Thread-safe for asyncio (single-threaded event loop assumption).
    Can be extended to use Redis for multi-process deployments.
    """

    def __init__(self):
        # OrderedDict used as LRU cache (most-recently-used at end)
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    def _evict_expired(self):
        """Remove expired sessions."""
        expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
        for sid in expired:
            del self._sessions[sid]

    def _evict_lru(self):
        """Evict least-recently-used sessions if at capacity."""
        while len(self._sessions) >= MAX_SESSIONS:
            self._sessions.popitem(last=False)

    def get_or_create(self, session_id: str) -> Session:
        """Get existing session or create a new one."""
        self._evict_expired()
        if session_id in self._sessions:
            session = self._sessions[session_id]
            # Move to end (most recently used)
            self._sessions.move_to_end(session_id)
            return session
        self._evict_lru()
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """Return session if it exists and isn't expired."""
        session = self._sessions.get(session_id)
        if session is None or session.is_expired():
            return None
        self._sessions.move_to_end(session_id)
        return session

    def delete(self, session_id: str):
        self._sessions.pop(session_id, None)

    def session_count(self) -> int:
        self._evict_expired()
        return len(self._sessions)
