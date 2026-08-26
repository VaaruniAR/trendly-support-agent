"""Return-reason collection and evidence gating.

This workflow deliberately runs outside the LLM.  The model can explain the
outcome, but cannot bypass the item/reason/evidence steps or create a return
without the customer completing them.
"""

from __future__ import annotations

import re
from typing import Any

from src.agent.state import ConversationState
from src.config import STATUS_LABELS
from src.data_loader import get_order_by_id
from src.tools.return_tools import DAMAGE_REASONS, check_return_eligibility, initiate_return

RETURN_INTENT = re.compile(r"\b(return|send\s+back|refund)\b", re.I)
AFFIRMATIVE = re.compile(r"\b(yes|yeah|yep|confirm|proceed|go ahead|do it)\b", re.I)


def _order_id_from_message(message: str) -> str | None:
    found = re.search(r"\bTR[-\s]?(\d{4})\b", message, re.I)
    return f"TR-{found.group(1)}" if found else None


def _reason_from_message(message: str) -> str | None:
    text = message.lower()
    if any(word in text for word in ("defect", "faulty", "not working", "broken")):
        return "defective"
    if any(word in text for word in ("damage", "damaged", "torn", "stain", "scratched")):
        return "damaged"
    if any(word in text for word in ("wrong item", "incorrect item", "different item")):
        return "wrong_item"
    if any(word in text for word in ("size", "fit", "change my mind", "don't want", "dont want", "no longer")):
        return "change_of_mind"
    return None


def _find_item(order: dict[str, Any], message: str) -> dict[str, Any] | None:
    text = message.lower()
    number = re.search(r"\b([1-9])\b", text)
    if number:
        index = int(number.group(1)) - 1
        if index < len(order["items"]):
            return order["items"][index]
    for item in order["items"]:
        if item["item_id"].lower() in text or item["name"].lower() in text:
            return item
    return None


def _items_prompt(order: dict[str, Any]) -> str:
    return f"Which item would you like to return from **{order['order_id']}**?"


def _item_choices(order: dict[str, Any]) -> list[dict[str, str]]:
    return [{"label": item["name"], "value": item["name"]} for item in order["items"]]


RETURN_REASON_CHOICES = [
    {"label": "Doesn't fit / changed my mind", "value": "doesn't fit"},
    {"label": "Damaged", "value": "damaged"},
    {"label": "Defective", "value": "defective"},
    {"label": "Wrong item received", "value": "wrong item received"},
]

RETURN_CONFIRMATION_CHOICES = [
    {"label": "Confirm return", "value": "confirm return"},
    {"label": "Not now", "value": "not now"},
]


def _reason_prompt(item: dict[str, Any]) -> str:
    return f"What is the reason for returning **{item['name']}**?"


def _not_delivered_reply(order: dict[str, Any]) -> str:
    """Explain why an undelivered order cannot enter the return flow yet."""
    if order["status"] == "cancelled":
        return "This order is cancelled, so a return cannot be raised for it."
    label = STATUS_LABELS.get(order["status"], order["status"].replace("_", " "))
    expected = order.get("expected_delivery")
    date = f" It is expected by **{expected}**." if expected else ""
    return (
        f"**{order['order_id']}** is currently **{label.lower()}**, not delivered yet.{date} "
        "A return can only be started after delivery. I can help you track the order in the meantime."
    )


def _action_result(result: dict[str, Any]) -> str:
    if result.get("success"):
        return (
            f"Your return is confirmed — **{result['return_id']}**. "
            f"{_customer_copy(result['message'])}"
        )
    return result.get("error", "I couldn't create that return. A support specialist can help.")


def _customer_copy(text: str) -> str:
    """Strip internal policy-section markers from deterministic customer copy."""
    return re.sub(r"\s*\(§\d+(?:\.\d+)?\)", "", text)


def _eligible_confirmation(state: ConversationState, order: dict[str, Any]) -> dict[str, Any]:
    intake = state.return_intake or {}
    result = check_return_eligibility(
        order["order_id"], [intake["item_id"]], intake["reason"]
    )
    if not result.get("eligible"):
        state.return_intake = None
        return {
            "reply": result.get("reason", "This item is not eligible for return."),
            "tool_calls": ["check_return_eligibility"],
        }
    state.return_intake["stage"] = "confirm"
    note = _customer_copy(result.get("refund_note") or "")
    return {
        "reply": (
            f"**{intake['item_name']}** is eligible for return. {note}\n\n"
            "Would you like me to confirm the return request?"
        ).strip(),
        "tool_calls": ["check_return_eligibility"],
        "choices": RETURN_CONFIRMATION_CHOICES,
    }


def handle_return_intake(state: ConversationState, message: str) -> dict[str, Any] | None:
    """Return a deterministic workflow response, or None for normal agent routing."""
    intake = state.return_intake
    starts_return = bool(RETURN_INTENT.search(message))
    if not intake and not starts_return:
        return None

    if not intake:
        order_id = _order_id_from_message(message) or state.active_order_id
        if not order_id:
            return {"reply": "I can help with that. Which order would you like to return an item from?"}
        order = get_order_by_id(order_id)
        if not order:
            return None  # Let the regular lookup tool issue the standard not-found result.
        if state.verified_email and order["customer_email"].lower() != state.verified_email.lower():
            return {"reply": "I can only help with returns for the signed-in customer's orders."}
        state.active_order_id = order_id
        if order["status"] != "delivered":
            return {"reply": _not_delivered_reply(order), "tool_calls": ["check_return_eligibility"]}
        if len(order["items"]) > 1:
            state.return_intake = {"order_id": order_id, "stage": "item"}
            return {"reply": _items_prompt(order), "choices": _item_choices(order)}
        item = order["items"][0]
        state.return_intake = {
            "order_id": order_id, "item_id": item["item_id"], "item_name": item["name"], "stage": "reason"
        }
        return {"reply": _reason_prompt(item), "choices": RETURN_REASON_CHOICES}

    order = get_order_by_id(intake["order_id"])
    if not order:
        state.return_intake = None
        return {"reply": "I can't find that order anymore. Please start the return again with the order ID."}

    if intake["stage"] == "item":
        item = _find_item(order, message)
        if not item:
            return {"reply": _items_prompt(order), "choices": _item_choices(order)}
        intake.update({"item_id": item["item_id"], "item_name": item["name"], "stage": "reason"})
        return {"reply": _reason_prompt(item), "choices": RETURN_REASON_CHOICES}

    if intake["stage"] == "reason":
        reason = _reason_from_message(message)
        if not reason:
            return {"reply": _reason_prompt({"name": intake["item_name"]}), "choices": RETURN_REASON_CHOICES}
        intake["reason"] = reason
        if reason in DAMAGE_REASONS:
            eligibility = check_return_eligibility(order["order_id"], [intake["item_id"]], reason)
            if not eligibility.get("eligible"):
                state.return_intake = None
                return {
                    "reply": eligibility.get("reason", "This item is not eligible for a return."),
                    "tool_calls": ["check_return_eligibility"],
                }
            intake["stage"] = "evidence"
            return {
                "reply": (
                    f"Thanks. For a {reason.replace('_', ' ')} item, Trendly requires photographs "
                    "within 48 hours of delivery. Please use the **Add photo** button to upload one clear photo "
                    f"of **{intake['item_name']}** showing the issue, with the product tag visible in the same photo."
                ),
                "awaiting_evidence": True,
                "tool_calls": ["check_return_eligibility"],
            }
        return _eligible_confirmation(state, order)

    if intake["stage"] == "confirm":
        if not AFFIRMATIVE.search(message):
            state.return_intake = None
            return {"reply": "No problem — I have not created a return. You can start one whenever you’re ready."}
        if not state.verified_email:
            return {"reply": "Please select your signed-in profile before I can confirm the return."}
        result = initiate_return(order["order_id"], [intake["item_id"]], intake["reason"], state.verified_email)
        state.return_intake = None
        return {"reply": _action_result(result), "tool_calls": ["initiate_return"]}

    if intake["stage"] == "evidence":
        return {"reply": "Please upload a clear photo of the product and its tag, with the issue visible, using **Add photo**. I’ll send it for review.", "awaiting_evidence": True}

    return None
