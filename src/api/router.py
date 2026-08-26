"""REST API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException
from groq import APIConnectionError, APIStatusError

from src.agent.state import session_store
from src.api.deps import get_agent, groq_http_error, require_agent, ssl_verify_label
from src.api.schemas import ChatRequest, ChatResponse, EvidenceRequest, EvidenceResponse
from src.config import ASSISTANT_NAME, STORE_NAME
from src.data_loader import get_catalog, get_customers
from src.env_loader import groq_key_hint, is_groq_key_configured
from src.services.evidence_review import review_return_evidence

router = APIRouter()


@router.get("/config/ui")
def ui_config() -> dict[str, str]:
    return {"assistant_name": ASSISTANT_NAME, "store_name": STORE_NAME}


@router.get("/customers")
def customers() -> dict[str, Any]:
    return {"customers": get_customers()}


@router.get("/catalog")
def catalog(customer_email: str | None = None) -> dict[str, Any]:
    return get_catalog(customer_email)


@router.get("/health")
def health() -> dict[str, str]:
    key_ok = is_groq_key_configured()
    return {
        "status": "ok",
        "llm_configured": str(get_agent() is not None),
        "groq_key_set": str(key_ok),
        "setup_hint": groq_key_hint() if not key_ok else "",
        "ssl_verify": ssl_verify_label(),
    }


@router.get("/sessions")
def list_sessions(customer_email: str | None = None) -> dict[str, Any]:
    sessions = session_store.list_sessions(customer_email)
    return {
        "sessions": [s.to_history_item() for s in sessions],
        "count": len(sessions),
    }


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = require_agent()
    is_new = req.session_id is None
    state = session_store.get(req.session_id) if req.session_id else session_store.create()
    if req.session_id and not state:
        raise HTTPException(status_code=404, detail="Session not found")

    if is_new and req.customer_email:
        state.verified_email = req.customer_email.strip().lower()
        state.customer_name = req.customer_name

    try:
        result = agent.run_turn(state, req.message)
    except (APIConnectionError, APIStatusError) as exc:
        raise groq_http_error(exc) from exc

    session_store.persist()
    return ChatResponse(
        session_id=state.session_id,
        reply=result["reply"],
        escalated=result.get("escalated", False),
        ticket_id=result.get("ticket_id"),
        awaiting_evidence=result.get("awaiting_evidence", False),
        choices=result.get("choices", []),
    )


@router.post("/evidence", response_model=EvidenceResponse)
def submit_return_evidence(req: EvidenceRequest) -> EvidenceResponse:
    state = session_store.get(req.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    result = review_return_evidence(state, req.data_url)
    session_store.persist()
    return EvidenceResponse(**result)


@router.get("/session/{session_id}")
def get_session(session_id: str, customer_email: str | None = None) -> dict[str, Any]:
    state = session_store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if customer_email is not None:
        owner = (state.verified_email or "").lower()
        if owner != customer_email.strip().lower():
            raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "title": state.title,
        "messages": state.ui_messages(),
        "escalated": state.escalated,
        "ticket_id": state.escalation_ticket,
        "awaiting_evidence": bool(state.return_intake and state.return_intake.get("stage") == "evidence"),
    }


@router.delete("/session/{session_id}")
def delete_session(session_id: str) -> dict[str, bool]:
    if not session_store.get(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    session_store.delete(session_id)
    return {"deleted": True}
