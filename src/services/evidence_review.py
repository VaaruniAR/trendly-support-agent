"""Safe local handling for return-evidence uploads.

A validated photo is written to the local, git-ignored evidence store
(src/services/evidence_store.py) along with the claim details, and the
resulting evidence record is linked to the specialist's escalation ticket.
This deployment deliberately routes every claim to a human reviewer rather
than making an automated authenticity judgement — the policy requires
photographs (§6.1) but does not define an automated image-approval standard.
"""

from __future__ import annotations

import base64
import re
from typing import Any

from src.agent.state import ConversationState
from src.services.evidence_store import EvidenceStorageError, attach_ticket, save_evidence
from src.tools.escalation_tools import escalate_to_human

MAX_IMAGE_BYTES = 5 * 1024 * 1024
DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)$", re.I)


def _decode_valid_image(data_url: str) -> tuple[bytes, str] | None:
    match = DATA_URL.match(data_url)
    if not match:
        return None
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except ValueError:
        return None
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return None
    mime = match.group(1).lower()
    valid = {
        "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
        "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
    }.get(mime, False)
    return (raw, mime) if valid else None


def review_return_evidence(state: ConversationState, data_url: str) -> dict[str, Any]:
    """Validate a photo, persist it to the local evidence store, and create a human-review handoff."""
    intake: dict[str, Any] = state.return_intake or {}
    if intake.get("stage") != "evidence":
        return {"reply": "I’m not waiting for a return photo right now. Start a return first and choose a defect, damage, or wrong-item reason."}
    if not state.verified_email:
        return {"reply": "Please select your signed-in profile before uploading return evidence.", "awaiting_evidence": True}
    image = _decode_valid_image(data_url)
    if not image:
        return {"reply": "Please upload a clear JPG, PNG, or WebP photo under 5 MB.", "awaiting_evidence": True}
    raw_image, mime_type = image
    try:
        evidence = save_evidence(
            raw_image,
            mime_type=mime_type,
            order_id=intake["order_id"],
            item_id=intake["item_id"],
            reason=intake["reason"],
            customer_email=state.verified_email,
        )
    except EvidenceStorageError as exc:
        return {"reply": str(exc), "awaiting_evidence": True}

    ticket = escalate_to_human(
        reason="Return evidence review required",
        summary=(
            f"Customer requested a return for {intake['item_name']} on {intake['order_id']} "
            f"because it is {intake['reason'].replace('_', ' ')}. The customer uploaded product/tag evidence "
            f"that is stored as evidence record {evidence['evidence_id']} and requires specialist review "
            "under the damaged/wrong-item process (§6.1)."
        ),
        customer_email=state.verified_email,
        order_id=intake["order_id"],
        priority="normal",
    )
    attach_ticket(evidence["evidence_id"], ticket["ticket_id"])
    state.escalated = True
    state.escalation_ticket = ticket["ticket_id"]
    state.evidence_ids.append(evidence["evidence_id"])
    state.return_intake = None
    reply = (
        f"Thanks — I’ve sent your product-and-tag photo to a human support specialist for review. "
        f"Your reference is **{ticket['ticket_id']}**. They’ll get back to you shortly."
    )
    state.add_message("assistant", reply)
    return {"reply": reply, "escalated": True, "ticket_id": ticket["ticket_id"]}
