"""Escalation tools — human handoff with structured ticket summaries."""
from datetime import datetime

from src.config import HIGH_VALUE_THRESHOLD
from src.data_loader import get_order_by_id

_escalation_log: list[dict] = []

BANK_DETAIL_PATTERNS = (
    "bank account",
    "account number",
    "ifsc",
    "routing number",
)


def escalate_to_human(
    reason: str,
    summary: str,
    customer_email: str | None = None,
    order_id: str | None = None,
    priority: str = "normal",
) -> dict:
    """
    Escalate the conversation to a human agent with a structured handoff summary.
    """
    ticket_id = f"ESC-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    handoff = {
        "ticket_id": ticket_id,
        "created_at": datetime.now().isoformat(),
        "reason": reason,
        "summary": summary,
        "customer_email": customer_email,
        "order_id": order_id,
        "priority": priority,
        "status": "queued_for_human",
    }

    if order_id:
        order = get_order_by_id(order_id)
        if order:
            if order["total_amount"] >= HIGH_VALUE_THRESHOLD:
                handoff["priority"] = "high"
                handoff["note"] = (
                    f"High-value order (₹{order['total_amount']}) — requires human review."
                )
            if order["status"] == "lost_in_transit":
                handoff["priority"] = "high"
                handoff["note"] = (
                    "Lost-parcel claim — human must offer replacement or refund (§1.6)."
                )
            if order.get("payment_method") == "cash_on_delivery":
                handoff["cod_refund"] = True
                handoff["note"] = (
                    (handoff.get("note", "") + " ")
                    + "COD refund — collect bank details via secure link (§3.3)."
                ).strip()

    _escalation_log.append(handoff)

    return {
        "escalated": True,
        "ticket_id": ticket_id,
        "message": (
            "I've connected you with a human support specialist. "
            f"Your reference number is {ticket_id}. "
            "Expected first response within 4 hours during 9 AM–9 PM IST."
        ),
        "handoff": handoff,
    }


def should_auto_escalate(
    order_id: str | None,
    contact_count: int,
    user_message: str,
) -> dict | None:
    """Deterministic pre-checks before LLM decides."""
    msg = user_message.lower()

    human_phrases = (
        "speak to a human",
        "speak to human",
        "talk to a human",
        "talk to human",
        "real person",
        "human agent",
        "human support",
        "connect me to",
        "transfer me",
        "manager",
    )
    if any(p in msg for p in human_phrases):
        return {"escalate": True, "reason": "Customer explicitly requested human agent"}

    if any(p in msg for p in ("lawyer", "legal action", "sue", "consumer court", "media", "twitter blast")):
        return {"escalate": True, "reason": "Legal/media complaint", "priority": "high"}

    if contact_count >= 3:
        return {"escalate": True, "reason": "3+ contacts on same issue"}

    if order_id:
        order = get_order_by_id(order_id)
        if order:
            if order["status"] == "lost_in_transit":
                return {
                    "escalate": True,
                    "reason": "Lost-parcel claim must be handled by human (§1.6)",
                    "priority": "high",
                }
            if order["total_amount"] >= HIGH_VALUE_THRESHOLD:
                return {
                    "escalate": True,
                    "reason": (
                        f"Order value ₹{order['total_amount']} exceeds "
                        f"₹{HIGH_VALUE_THRESHOLD:,} threshold"
                    ),
                }

    if any(p in msg for p in BANK_DETAIL_PATTERNS):
        return {
            "escalate": True,
            "reason": "Customer attempting to share bank details — route to secure human channel (§3.3)",
            "priority": "high",
        }

    return None


def clear_escalation_log() -> None:
    _escalation_log.clear()
