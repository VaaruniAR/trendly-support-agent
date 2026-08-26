"""
Application constants — single source of truth for paths, LLM settings, and policy rules.

Tools import from here instead of hardcoding values so policy changes stay in one place.
"""

import os
from pathlib import Path

# --- File paths (relative to project root) ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
POLICY_PATH = DATA_DIR / "trendly_policy.md"   # Official Trendly policy (read-only)
ORDERS_PATH = DATA_DIR / "orders.json"         # Eval dataset — do not edit for submission
# Tests can point this at an isolated temp file; normal runs keep the local
# conversation history in data/chat_sessions.json.
SESSIONS_PATH = Path(os.getenv("TRENDLY_SESSIONS_PATH", DATA_DIR / "chat_sessions.json"))
# Demo evidence storage: image files plus a small JSON registry used by the
# local human-review handoff. Both paths are git-ignored and never public URLs.
EVIDENCE_DIR = Path(os.getenv("TRENDLY_EVIDENCE_DIR", DATA_DIR / "return_evidence"))
EVIDENCE_INDEX_PATH = Path(os.getenv("TRENDLY_EVIDENCE_INDEX_PATH", DATA_DIR / "evidence_records.json"))

# --- Branding shown in UI and API titles ---
ASSISTANT_NAME = "Aria"
STORE_NAME = "Trendly"

# Fixed "today" for return-window math — matches assignment eval date in prompts
REFERENCE_DATE = "2026-07-26"

# --- LLM (Groq) settings ---
LLM_MODEL = "openai/gpt-oss-120b"
MAX_AGENT_ITERATIONS = 8  # ReAct loop cap — escalate if exceeded

# --- Business rules mirrored from trendly_policy.md ---
RETURN_WINDOW_DAYS = 30
HIGH_VALUE_THRESHOLD = 25000  # Orders above this auto-escalate to human

# Policy §2.3 — non-returnable categories (matched case-insensitively)
EXCLUDED_CATEGORIES = {
    "innerwear",
    "jewellery",
    "beauty and fragrance products",
    "face masks",
    "gift cards",
}

STATUS_LABELS = {
    "in_transit": "In transit",
    "delivered": "Delivered",
    "partially_shipped": "Partially shipped",
    "delayed": "Delayed",
    "lost_in_transit": "Lost in transit",
    "cancelled": "Cancelled",
}
