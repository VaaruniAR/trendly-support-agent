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


def test_partially_shipped_gives_item_specific_answer_for_unshipped_item(orders):
    """A partially-shipped order must not be treated as fully dispatched — the
    customer's own unshipped item should get an item-specific, still-pending answer
    on the first turn, not the order-level 'already in the delivery process' framing."""
    order = next(o for o in orders.values() if o["status"] == "partially_shipped")
    unshipped = next(i for i in order["items"] if not i.get("shipped"))
    result = cancellation_response(order["order_id"], f"cancel my {unshipped['name']}")
    assert "back-order" in result["reply"].lower() or "backorder" in result["reply"].lower()
    assert "already in the delivery process" not in result["reply"]
    assert unshipped["name"] in result["reply"]


def test_partially_shipped_gives_item_specific_answer_for_shipped_item(orders):
    """The already-shipped item in the same order should still get the dispatched framing."""
    order = next(o for o in orders.values() if o["status"] == "partially_shipped")
    shipped = next(i for i in order["items"] if i.get("shipped"))
    result = cancellation_response(order["order_id"], f"cancel my {shipped['name']}")
    assert "already in the delivery process" in result["reply"]
    assert shipped["name"] in result["reply"]


def test_partially_shipped_without_named_item_asks_which_one(orders):
    order = next(o for o in orders.values() if o["status"] == "partially_shipped")
    result = cancellation_response(order["order_id"], "I want to cancel my order")
    assert "which item" in result["reply"].lower()
    assert "already in the delivery process" not in result["reply"]
