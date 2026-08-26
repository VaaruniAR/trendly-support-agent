"""Side effects from tool calls — session memory and auto-escalation rules."""

from __future__ import annotations

import json
from typing import Any

from src.agent.state import ConversationState
from src.tools.escalation_tools import escalate_to_human


def apply_tool_args(state: ConversationState, name: str, args: dict[str, Any]) -> None:
    """Update session memory from tool arguments before execution."""
    if name == "lookup_order":
        if email := args.get("customer_email"):
            state.verified_email = email.strip().lower()
        if order_id := args.get("order_id"):
            state.active_order_id = order_id.strip().upper()
    elif name == "initiate_return" and args.get("customer_email"):
        state.verified_email = args["customer_email"].strip().lower()
    elif name == "escalate_to_human":
        state.escalated = True


def apply_tool_result(state: ConversationState, name: str, result_json: str) -> None:
    """Update session from tool output after execution."""
    if name != "escalate_to_human":
        return
    parsed = json.loads(result_json)
    state.escalation_ticket = parsed.get("ticket_id")


def check_lost_parcel_escalation(
    state: ConversationState,
    result_json: str,
) -> dict[str, Any] | None:
    """
    After lookup_order, auto-escalate lost-in-transit orders (§1.6).
    Returns a turn result dict when escalation fires, else None.
    """
    if state.escalated:
        return None

    parsed = json.loads(result_json)
    order_data = parsed.get("order", {})
    if not (parsed.get("found") and order_data.get("requires_escalation")):
        return None

    esc = escalate_to_human(
        reason="Lost-parcel claim (§1.6)",
        summary=(
            f"Order {order_data.get('order_id')} marked lost in transit. "
            "Customer needs replacement or refund via human agent."
        ),
        customer_email=state.verified_email,
        order_id=order_data.get("order_id"),
        priority="high",
    )
    state.escalated = True
    state.escalation_ticket = esc["ticket_id"]
    reply = esc["message"] + "\n\nA specialist will handle your lost-parcel claim shortly."
    state.add_message("assistant", reply)
    return {
        "reply": reply,
        "escalated": True,
        "ticket_id": esc["ticket_id"],
        "tool_calls": ["lookup_order", "escalate_to_human"],
    }


def build_context_message(state: ConversationState) -> str:
    """Inject session memory as a supplemental system message."""
    parts = []
    if state.verified_email:
        signed_in = f" — signed in as {state.customer_name}" if state.customer_name else ""
        parts.append(f"Verified customer email: {state.verified_email}{signed_in}")
    if state.active_order_id:
        parts.append(f"Active order: {state.active_order_id}")
    parts.append(f"Contact count this session: {state.contact_count}")
    if state.escalated:
        parts.append(f"Already escalated: ticket {state.escalation_ticket}")
    return "Session context: " + "; ".join(parts) if parts else ""
