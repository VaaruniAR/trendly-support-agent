"""
Conversation session state — persisted chat history (unlimited).

Two storage backends, chosen automatically:
  - Postgres, when DATABASE_URL is set. This is what makes chat history
    survive on the live Render deployment: Render's free web services wipe
    the local filesystem on every spin-down (not just on redeploy), so a
    JSON file on disk resets after ~15 minutes of inactivity.
  - A local JSON file (data/chat_sessions.json), used when no DATABASE_URL
    is set — e.g. for local development, where the process itself doesn't
    get recycled the same way.

Either way, this module's public surface (SessionStore.create/get/delete/
list_sessions/persist/clear_all) is unchanged, so nothing outside this file
needs to know which backend is active. A database hiccup never breaks an
in-progress chat: every backend call is wrapped so a failed read/write is
logged and the conversation just continues without that turn's history
being saved, rather than the request failing.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.config import DATABASE_URL, SESSIONS_PATH
from src.utils.dates import parse_dt, utc_now

logger = logging.getLogger(__name__)


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


class _FileBackend:
    """Local JSON file persistence — data/chat_sessions.json.

    Used when DATABASE_URL isn't set. Matches the original single-file
    behavior this app shipped with: every persist() rewrites the full set
    of active sessions.
    """

    def load_all(self) -> list[dict[str, Any]]:
        if not SESSIONS_PATH.is_file():
            return []
        try:
            raw = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
            return list(raw.get("sessions", []))
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def save_all(self, sessions: list[dict[str, Any]]) -> None:
        payload = {"sessions": sessions}
        SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSIONS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def delete(self, session_id: str) -> None:
        # SessionStore.delete() always calls persist()-equivalent save_all()
        # right after via the caller's own full rewrite, so there is nothing
        # to do per-row for the file backend.
        pass

    def clear_all(self) -> None:
        if SESSIONS_PATH.is_file():
            SESSIONS_PATH.unlink()


def _normalize_dsn(url: str) -> str:
    # Render (and Heroku-style) connection strings sometimes use the
    # postgres:// scheme, which older psycopg2 releases reject in favour of
    # postgresql://. Normalize so either form works.
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


class _PostgresBackend:
    """
    Postgres persistence — survives Render free-tier spin-downs, which wipe
    local disk on every idle timeout, not just on redeploy (see
    SOLUTION.md). Set DATABASE_URL to a Postgres connection string (e.g. a
    free Render Postgres instance's Internal Database URL) to enable this.
    """

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            verified_email TEXT,
            updated_at TIMESTAMPTZ NOT NULL,
            data JSONB NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_email
            ON chat_sessions (verified_email);
    """

    def __init__(self, database_url: str) -> None:
        import psycopg2  # imported lazily — the file backend never needs it installed

        self._psycopg2 = psycopg2
        self._dsn = _normalize_dsn(database_url)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(self._SCHEMA)

    @contextmanager
    def _connection(self):
        # psycopg2 connections used as a `with` block only manage the
        # transaction (commit on success, rollback on exception) — they do
        # NOT close the connection. Opening one connection per call and
        # relying on `with conn:` alone would leak a connection every turn,
        # so close is handled explicitly here regardless of outcome.
        conn = self._psycopg2.connect(self._dsn, connect_timeout=5)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def load_all(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM chat_sessions ORDER BY updated_at DESC")
                return [row[0] for row in cur.fetchall()]

    def save_all(self, sessions: list[dict[str, Any]]) -> None:
        if not sessions:
            return
        with self._connection() as conn:
            with conn.cursor() as cur:
                for s in sessions:
                    cur.execute(
                        """
                        INSERT INTO chat_sessions (session_id, verified_email, updated_at, data)
                        VALUES (%s, %s, %s::timestamptz, %s::jsonb)
                        ON CONFLICT (session_id) DO UPDATE
                        SET verified_email = EXCLUDED.verified_email,
                            updated_at = EXCLUDED.updated_at,
                            data = EXCLUDED.data
                        """,
                        (s["session_id"], s.get("verified_email"), s["updated_at"], json.dumps(s)),
                    )

    def delete(self, session_id: str) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))

    def clear_all(self) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_sessions")


def _make_backend() -> _FileBackend | _PostgresBackend:
    if DATABASE_URL:
        try:
            return _PostgresBackend(DATABASE_URL)
        except Exception:
            logger.exception(
                "Could not connect using DATABASE_URL; falling back to local-file "
                "session storage, so chat history will NOT persist across restarts "
                "until this is fixed."
            )
    return _FileBackend()


class SessionStore:
    """Session registry with disk/DB persistence — all chats kept."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationState] = {}
        self._backend = _make_backend()
        self._load()

    def _active_sessions(self) -> list[ConversationState]:
        return [s for s in self._sessions.values() if s.ui_messages()]

    def _load(self) -> None:
        try:
            raw_sessions = self._backend.load_all()
        except Exception:
            logger.exception("Failed to load chat sessions from storage backend; starting empty.")
            return
        for item in raw_sessions:
            try:
                state = ConversationState.from_dict(item)
            except (KeyError, TypeError):
                continue
            if state.ui_messages():
                self._sessions[state.session_id] = state

    def _save_to_disk(self) -> None:
        # Kept as a private alias so persist() reads the same either way;
        # despite the name, this now goes through whichever backend is active.
        active = sorted(self._active_sessions(), key=lambda s: s.updated_at, reverse=True)
        self._backend.save_all([s.to_dict() for s in active])

    def persist(self) -> None:
        try:
            self._save_to_disk()
        except Exception:
            logger.exception(
                "Failed to persist chat sessions this turn; the conversation "
                "continues, but this turn's history may not be saved."
            )

    def create(self) -> ConversationState:
        session_id = str(uuid.uuid4())
        state = ConversationState(session_id=session_id)
        self._sessions[session_id] = state
        return state

    def get(self, session_id: str) -> ConversationState | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        try:
            self._backend.delete(session_id)
            self._save_to_disk()
        except Exception:
            logger.exception("Failed to delete session %s from storage backend.", session_id)

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
        try:
            self._backend.clear_all()
        except Exception:
            logger.exception("Failed to clear chat sessions in storage backend.")


session_store = SessionStore()
