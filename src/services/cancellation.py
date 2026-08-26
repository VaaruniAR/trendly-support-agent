"""Cancellation requests grounded strictly in the supplied Trendly policy."""

from __future__ import annotations

from src.data_loader import get_order_by_id


def cancellation_response(order_id: str | None) -> dict[str, str] | None:
    """Give a non-hallucinated cancellation response without needless escalation."""
    if not order_id:
        return {"reply": "I can check that for you. Which order would you like to cancel?"}
    order = get_order_by_id(order_id)
    if not order:
        return None
    if order["status"] == "cancelled":
        return {"reply": "This order is already cancelled. A return cannot be raised for a cancelled order."}

    dispatched = order["status"] in {"in_transit", "partially_shipped", "delayed", "lost_in_transit"}
    if dispatched:
        return {
            "reply": (
                f"**{order['order_id']}** is already in the delivery process. Trendly’s available policy does not say "
                "whether an order can be cancelled after dispatch, so I can’t promise a cancellation. "
                "It does say that an address cannot be changed after dispatch; in that case, the customer must refuse delivery and reorder. "
                "If you want a person to check a cancellation exception, ask me to connect you to support."
            )
        }
    return {
        "reply": (
            "The available Trendly policy does not describe cancellation eligibility or a cancellation process for this order, "
            "so I can’t confirm that it can be cancelled. If you want a person to check an exception, ask me to connect you to support."
        )
    }
