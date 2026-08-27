"""
Chat-history persistence: the JSON-file backend used for local development,
and the storage-backend abstraction that lets SessionStore also persist to
Postgres (src.agent.state._PostgresBackend) when DATABASE_URL is set.

There's no live Postgres reachable from a test run, so Postgres-specific
behavior is exercised through a fake backend that implements the same
load_all/save_all/delete/clear_all contract _PostgresBackend does — this
verifies SessionStore's orchestration is genuinely backend-agnostic, which
is the actual property that makes swapping storage backends safe.
"""
from __future__ import annotations

import json

import pytest

from src.agent import state as state_module
from src.agent.state import SessionStore


@pytest.fixture
def isolated_sessions_path(tmp_path, monkeypatch):
    path = tmp_path / "chat_sessions.json"
    monkeypatch.setattr(state_module, "SESSIONS_PATH", path)
    return path


class FakeDBBackend:
    """Implements the same 4-method contract _PostgresBackend does, backed
    by an in-memory dict instead of a real network round trip."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def load_all(self):
        return list(self.rows.values())

    def save_all(self, sessions):
        for s in sessions:
            self.rows[s["session_id"]] = s

    def delete(self, session_id):
        self.rows.pop(session_id, None)

    def clear_all(self):
        self.rows.clear()


def _store_with_backend(backend) -> SessionStore:
    store = SessionStore.__new__(SessionStore)
    store._sessions = {}
    store._backend = backend
    store._load()
    return store


# --- _FileBackend, exercised through the real SessionStore -----------------

def test_file_backend_persists_across_a_fresh_sessionstore(isolated_sessions_path):
    store = SessionStore()
    convo = store.create()
    convo.verified_email = "marcus@example.com"
    convo.add_message("user", "Where is my order?")
    convo.add_message("assistant", "Let me check.")
    store.persist()

    assert isolated_sessions_path.is_file()

    # Simulates a process restart: a fresh SessionStore re-reads from disk.
    reloaded_store = SessionStore()
    history = reloaded_store.list_sessions("marcus@example.com")
    assert len(history) == 1
    assert history[0].ui_messages() == convo.ui_messages()


def test_file_backend_never_persists_a_session_with_no_real_messages(isolated_sessions_path):
    store = SessionStore()
    store.create()  # no messages added
    store.persist()

    payload = json.loads(isolated_sessions_path.read_text())
    assert payload["sessions"] == []


def test_file_backend_delete_removes_session_from_disk(isolated_sessions_path):
    store = SessionStore()
    convo = store.create()
    convo.verified_email = "marcus@example.com"
    convo.add_message("user", "hi")
    store.persist()

    store.delete(convo.session_id)

    payload = json.loads(isolated_sessions_path.read_text())
    assert payload["sessions"] == []


def test_chat_history_is_private_per_profile(isolated_sessions_path):
    store = SessionStore()
    for email in ("marcus@example.com", "priya@example.com"):
        convo = store.create()
        convo.verified_email = email
        convo.add_message("user", f"hi, I'm {email}")
        store.persist()

    assert len(store.list_sessions("marcus@example.com")) == 1
    assert len(store.list_sessions("priya@example.com")) == 1
    assert store.list_sessions("marcus@example.com")[0].verified_email == "marcus@example.com"


# --- backend-agnostic orchestration, exercised against a fake DB-shaped backend ---

def test_sessionstore_orchestration_is_backend_agnostic():
    """The exact scenario DATABASE_URL is meant to fix: history surviving a
    fresh process, verified against the same 4-method contract
    _PostgresBackend implements (load_all/save_all/delete/clear_all)."""
    backend = FakeDBBackend()
    store = _store_with_backend(backend)

    convo = store.create()
    convo.verified_email = "priya@example.com"
    convo.add_message("user", "Can I return this jewellery?")
    convo.add_message("assistant", "That category is excluded from returns per policy.")
    store.persist()

    assert len(backend.rows) == 1

    # A brand new SessionStore reading the SAME backend simulates a fresh
    # container after a Render spin-down — this is the behavior the
    # DATABASE_URL-backed Postgres path exists to guarantee in production.
    fresh_store = _store_with_backend(backend)
    history = fresh_store.list_sessions("priya@example.com")
    assert len(history) == 1
    assert history[0].ui_messages() == convo.ui_messages()
    assert fresh_store.list_sessions("marcus@example.com") == []


def test_persist_does_not_raise_when_backend_fails():
    class ExplodingBackend(FakeDBBackend):
        def save_all(self, sessions):
            raise RuntimeError("simulated DB outage")

    store = _store_with_backend(ExplodingBackend())
    convo = store.create()
    convo.add_message("user", "hi")

    store.persist()  # must not raise — a DB hiccup should not break the chat turn


def test_load_does_not_raise_when_backend_fails():
    class ExplodingBackend(FakeDBBackend):
        def load_all(self):
            raise RuntimeError("simulated DB outage")

    store = _store_with_backend(ExplodingBackend())  # must not raise
    assert store.list_sessions("marcus@example.com") == []
