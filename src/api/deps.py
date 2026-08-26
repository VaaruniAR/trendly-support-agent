"""FastAPI dependencies — agent lifecycle and error mapping."""

import os

from fastapi import HTTPException
from groq import APIConnectionError, APIStatusError

from src.agent.orchestrator import SupportAgent
from src.env_loader import is_groq_key_configured

_agent: SupportAgent | None = None


def get_agent() -> SupportAgent | None:
    return _agent


def set_agent(agent: SupportAgent | None) -> None:
    global _agent
    _agent = agent


def require_agent() -> SupportAgent:
    if _agent is not None:
        return _agent
    if not is_groq_key_configured():
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY missing. Edit .env with gsk_... from https://console.groq.com",
        )
    raise HTTPException(status_code=503, detail="Agent failed to start. Restart ./run.sh")


def groq_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, APIConnectionError):
        err = str(exc).lower()
        detail = (
            "SSL error — add GROQ_SSL_VERIFY=false to .env and restart"
            if "certificate" in err or "ssl" in err
            else "Cannot reach Groq — try off VPN or allowlist api.groq.com"
        )
        return HTTPException(status_code=502, detail=detail)
    code = getattr(exc, "status_code", 0)
    if code == 401:
        return HTTPException(status_code=502, detail="Invalid GROQ_API_KEY")
    if code == 429:
        return HTTPException(
            status_code=429,
            detail="Groq's free-tier rate limit was hit (too many requests/tokens today). "
                   "Wait a minute and try again, or check https://console.groq.com/settings/billing.",
        )
    return HTTPException(status_code=502, detail=f"Groq error: {getattr(exc, 'message', exc)}")


def ssl_verify_label() -> str:
    return os.getenv("GROQ_SSL_VERIFY", "true")
