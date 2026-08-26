"""Cancellation requests grounded strictly in the supplied Trendly policy."""

from __future__ import annotations

from src.data_loader import get_order_by_id

DISPATCHED_STATUSES = {"in_transit", "delayed", "lost_in_transit"}


def _find_item(order: dict, message: str) -> dict | None:
    """Best-effort match of a specific line item mentioned in the customer's message."""
    text = (message or "").lower()
    for item in order["items"]:
        if item["name"].lower() in text:
            return item
    for item in order["items"]:
        words = [w for w in item["name"].lower().split() if len(w) >= 4]
        if any(w in text for w in words):
            return item
    return None


def _item_reply(order: dict, item: dict) -> str:
    name = item["name"]
    if item.get("shipped") is False:
        return (
            f"**{order['order_id']}** — **{name}** is still on back-order and has not shipped yet. "
            "Trendly's available policy does not describe a cancellation process for items pending "
            "shipment, so I'm not able to confirm or process a cancellation myself. "
            "If you'd like a team member to check whether it can be removed from the order, "
            "ask me to connect you to support."
        )
    # shipped is True, or unknown on a non-split order — treat as already dispatched.
    return (
        f"**{order['order_id']}** — **{name}** is already in the delivery process. Trendly's available "
        "policy does not say whether an order can be cancelled after dispatch, so I can't promise a "
        "cancellation. It does say that an address cannot be changed after dispatch; in that case, the "
        "customer must refuse delivery and reorder. If you want a person to check a cancellation "
        "exception, ask me to connect you to support."
    )


def cancellation_response(order_id: str | None, message: str = "") -> dict[str, str] | None:
    """Give a non-hallucinated cancellation response without needless escalation."""
    if not order_id:
        return {"reply": "I can check that for you. Which order would you like to cancel?"}
    order = get_order_by_id(order_id)
    if not order:
        return None
    if order["status"] == "cancelled":
        return {"reply": "This order is already cancelled. A return cannot be raised for a cancelled order."}

    if order["status"] == "partially_shipped":
        item = _find_item(order, message)
        if item is not None:
            return {"reply": _item_reply(order, item)}
        return {
            "reply": (
                f"**{order['order_id']}** is partially shipped — some items have already gone out, "
                "others are still on back-order. Trendly's available policy doesn't describe a "
                "cancellation process either way, so I can't confirm or process one directly. "
                "Let me know which item you mean, or ask me to connect you to a specialist who can "
                "check the whole order."
            )
        }

    dispatched = order["status"] in DISPATCHED_STATUSES
    if dispatched:
        return {
            "reply": (
                f"**{order['order_id']}** is already in the delivery process. Trendly's available policy does not say "
                "whether an order can be cancelled after dispatch, so I can't promise a cancellation. "
                "It does say that an address cannot be changed after dispatch; in that case, the customer must refuse delivery and reorder. "
                "If you want a person to check a cancellation exception, ask me to connect you to support."
            )
        }
    return {
        "reply": (
            "The available Trendly policy does not describe cancellation eligibility or a cancellation process for this order, "
            "so I can't confirm that it can be cancelled. If you want a person to check an exception, ask me to connect you to support."
        )
    }
