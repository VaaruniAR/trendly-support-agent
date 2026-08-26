"""
Load .env from project root before any other module reads os.environ.

Imported as a side effect in main.py and orchestrator.py so uvicorn/IDE starts
still pick up GROQ_API_KEY even when run.sh is not used.
"""

from pathlib import Path

from dotenv import load_dotenv

# Project root is one level above src/
_ROOT = Path(__file__).resolve().parent.parent
# override=True — .env file wins over empty shell vars (common when IDE starts uvicorn)
load_dotenv(_ROOT / ".env", override=True)


def is_groq_key_configured() -> bool:
    """True when a real Groq key is present (not empty or the .env.example placeholder)."""
    import os

    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return False
    if key == "your_groq_api_key_here":
        return False
    # Groq keys always start with gsk_
    if not key.startswith("gsk_"):
        return False
    return True


def groq_key_hint() -> str:
    """Human-readable hint for health/UI when the key is missing or invalid."""
    import os

    key = os.getenv("GROQ_API_KEY", "").strip()
    env_path = _ROOT / ".env"
    if not env_path.is_file():
        return f"Create {env_path.name} from .env.example and set GROQ_API_KEY=gsk_..."
    if not key or key == "your_groq_api_key_here":
        return "Edit .env — replace the placeholder with your key from console.groq.com"
    if not key.startswith("gsk_"):
        return "GROQ_API_KEY in .env must start with gsk_"
    return ""
