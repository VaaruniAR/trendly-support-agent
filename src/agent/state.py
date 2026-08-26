"""
Conversation session state — persisted chat history (unlimited).

Sessions survive server restarts via data/chat_sessions.json.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.config import SESSIONS_PATH
from src.utils.dates import parse_dt, utc_now


@dataclass
class ConversationState:
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    verified_email: str | None = None
    customer_name: str | None = None
    active_order_id: str | None = None
    contact_count: int = 1
    escalated: bool = False
    escalation_ticket: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    # Structured return intake gates action execution.  A return cannot be
    # created until the customer has selected an item, given a reason, and—if
    # it is a defect/damage claim—supplied usable evidence required by §6.1.
    return_intake: dict[str, Any] | None = None
    title: str = "New conversation"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def add_message(self, role: str, content: str, **extra: Any) -> None:
        msg: dict[str, Any] = {"role": role, "content": content}
        msg.update(extra)
        self.messages.append(msg)
        self.updated_at = utc_now()
        if role == "user" and self.title == "New conversation":
            preview = content.strip().replace("\n", " ")
            self.title = preview[:48] + ("…" if len(preview) > 48 else "")

    def ui_messages(self) -> list[dict[str, str]]:
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.messages
            if m["role"] in ("user", "assistant") and m.get("content")
        ]

    def to_history_item(self) -> dict[str, Any]:
        msgs = self.ui_messages()
        search_parts = [self.title] + [m["content"] for m in msgs]
        return {
            "session_id": self.session_id,
            "title": self.title,
            "updated_at": self.updated_at.isoformat(),
            "message_count": len(msgs),
            "escalated": self.escalated,
            "search_text": " ".join(search_parts).lower(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "verified_email": self.verified_email,
            "customer_name": self.customer_name,
            "active_order_id": self.active_order_id,
            "contact_count": self.contact_count,
            "escalated": self.escalated,
            "escalation_ticket": self.escalation_ticket,
            "evidence_ids": self.evidence_ids,
            "return_intake": self.return_intake,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationState:
        return cls(
            session_id=data["session_id"],
            messages=list(data.get("messages", [])),
            verified_email=data.get("verified_email"),
            customer_name=data.get("customer_name"),
            active_order_id=data.get("active_order_id"),
            contact_count=data.get("contact_count", 1),
            escalated=data.get("escalated", False),
            escalation_ticket=data.get("escalation_ticket"),
            evidence_ids=list(data.get("evidence_ids", [])),
            return_intake=data.get("return_intake"),
            title=data.get("title", "New conversation"),
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
        )


class SessionStore:
    """Session registry with disk persistence — all chats kept."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationState] = {}
        self._load_from_disk()

    def _active_sessions(self) -> list[ConversationState]:
        return [s for s in self._sessions.values() if s.ui_messages()]

    def _load_from_disk(self) -> None:
        if not SESSIONS_PATH.is_file():
            return
        try:
            raw = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
            for item in raw.get("sessions", []):
                state = ConversationState.from_dict(item)
                if state.ui_messages():
                    self._sessions[state.session_id] = state
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    def _save_to_disk(self) -> None:
        active = sorted(self._active_sessions(), key=lambda s: s.updated_at, reverse=True)
        payload = {"sessions": [s.to_dict() for s in active]}
        SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSIONS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def persist(self) -> None:
        self._save_to_disk()

    def create(self) -> ConversationState:
        session_id = str(uuid.uuid4())
        state = ConversationState(session_id=session_id)
        self._sessions[session_id] = state
        return state

    def get(self, session_id: str) -> ConversationState | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._save_to_disk()

    def list_sessions(self, customer_email: str | None = None) -> list[ConversationState]:
        """Chats are private per signed-in profile — no profile means no history."""
        if not customer_email:
            return []
        email = customer_email.strip().lower()
        owned = [
            s for s in self._active_sessions()
            if s.verified_email and s.verified_email.lower() == email
        ]
        return sorted(owned, key=lambda s: s.updated_at, reverse=True)

    def clear_all(self) -> None:
        self._sessions.clear()
        if SESSIONS_PATH.is_file():
            SESSIONS_PATH.unlink()


session_store = SessionStore()
