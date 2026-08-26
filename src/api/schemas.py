"""Request/response models for the REST API."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    customer_email: str | None = None
    customer_name: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    escalated: bool = False
    ticket_id: str | None = None
    awaiting_evidence: bool = False
    choices: list[dict[str, str]] = []


class EvidenceRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    data_url: str = Field(..., min_length=32, max_length=7_000_000)


class EvidenceResponse(BaseModel):
    reply: str
    escalated: bool = False
    ticket_id: str | None = None
    awaiting_evidence: bool = False
