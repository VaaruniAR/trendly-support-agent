"""Cancellation behaviour must remain grounded in the supplied policy."""

from src.services.cancellation import cancellation_response


def test_dispatched_cancellation_does_not_invent_a_policy_rule(orders):
    order = next(o for o in orders.values() if o["status"] == "in_transit")
    result = cancellation_response(order["order_id"])
    assert "does not say" in result["reply"]
    assert "address cannot be changed after dispatch" in result["reply"]
    assert "human agent" not in result["reply"].lower()


def test_cancelled_order_is_explained_without_escalation(orders):
    order = next(o for o in orders.values() if o["status"] == "cancelled")
    result = cancellation_response(order["order_id"])
    assert "already cancelled" in result["reply"].lower()
