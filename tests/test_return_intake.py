"""Return-reason/evidence workflow regression tests."""

import base64

from src.agent.state import ConversationState
from src.services.evidence_review import review_return_evidence
from src.services.return_intake import handle_return_intake
from src.tools.return_tools import check_return_eligibility


def _state(order):
    return ConversationState(
        session_id="return-intake-test",
        verified_email=order["customer_email"],
        active_order_id=order["order_id"],
    )


def test_return_collects_item_then_reason_for_multi_item_order(orders):
    order = next(o for o in orders.values() if len(o["items"]) > 1 and o["status"] == "delivered")
    state = _state(order)
    first = handle_return_intake(state, f"I want to return {order['order_id']}")
    assert "Which item" in first["reply"]
    assert state.return_intake["stage"] == "item"

    second = handle_return_intake(state, "1")
    assert "reason" in second["reply"].lower()
    assert state.return_intake["stage"] == "reason"


def test_return_for_undelivered_order_explains_status_before_reason(orders):
    order = next(o for o in orders.values() if o["status"] == "in_transit")
    state = _state(order)
    result = handle_return_intake(state, f"I want to return {order['order_id']}")
    assert "not delivered yet" in result["reply"]
    assert "reason for returning" not in result["reply"].lower()
    assert state.return_intake is None


def test_damage_reason_requires_tagged_product_photo(orders):
    order = next(
        o for o in orders.values()
        if o["status"] == "delivered" and o.get("delivered_at") >= "2026-07-24"
    )
    state = _state(order)
    handle_return_intake(state, f"I want to return {order['order_id']}")
    if state.return_intake["stage"] == "item":
        handle_return_intake(state, "1")
    result = handle_return_intake(state, "The item is damaged")
    assert result["awaiting_evidence"] is True
    assert "tag visible" in result["reply"].lower()
    assert state.return_intake["stage"] == "evidence"


def test_fit_reason_requests_confirmation_before_placing_return(orders):
    order = next(
        o for o in orders.values()
        if o["status"] == "delivered" and o.get("delivered_at") >= "2026-06-26"
        and not o["items"][0].get("final_sale")
    )
    state = _state(order)
    handle_return_intake(state, f"I want to return {order['order_id']}")
    if state.return_intake["stage"] == "item":
        handle_return_intake(state, order["items"][0]["name"])
    result = handle_return_intake(state, "doesn't fit")
    assert "confirm the return" in result["reply"].lower()
    assert result["tool_calls"] == ["check_return_eligibility"]
    assert state.return_intake["stage"] == "confirm"

    confirmed = handle_return_intake(state, "confirm return")
    assert "return is confirmed" in confirmed["reply"].lower()
    assert confirmed["tool_calls"] == ["initiate_return"]


def test_invalid_evidence_keeps_photo_step(orders):
    order = next(o for o in orders.values() if o["status"] == "delivered")
    state = _state(order)
    state.return_intake = {
        "order_id": order["order_id"], "item_id": order["items"][0]["item_id"],
        "item_name": order["items"][0]["name"], "reason": "damaged", "stage": "evidence",
    }
    result = review_return_evidence(state, "data:image/png;base64,not-an-image")
    assert result["awaiting_evidence"] is True
    assert state.return_intake["stage"] == "evidence"


def test_valid_evidence_is_stored_then_escalated(orders, monkeypatch):
    order = next(o for o in orders.values() if o["status"] == "delivered")
    state = _state(order)
    state.return_intake = {
        "order_id": order["order_id"], "item_id": order["items"][0]["item_id"],
        "item_name": order["items"][0]["name"], "reason": "damaged", "stage": "evidence",
    }
    monkeypatch.setattr(
        "src.services.evidence_review.save_evidence",
        lambda *args, **kwargs: {"evidence_id": "EVD-TEST-001"},
    )
    monkeypatch.setattr("src.services.evidence_review.attach_ticket", lambda *args, **kwargs: None)
    # Minimal syntactically valid PNG header; no real customer content stored.
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nexample").decode()
    result = review_return_evidence(state, f"data:image/png;base64,{png}")
    assert result["escalated"] is True
    assert result["ticket_id"].startswith("ESC-")
    assert "product-and-tag photo" in result["reply"].lower()
    assert state.return_intake is None
    assert state.evidence_ids == ["EVD-TEST-001"]
    assert "data:image" not in str(state.to_dict())


def test_final_sale_item_explains_why_before_asking_reason(orders):
    """Final Sale eligibility never depends on the return reason, so the customer
    should get the explanation immediately — not a bare 'not eligible for return'
    that only gets explained after they ask 'why?'."""
    order = next(
        o for o in orders.values()
        if o["status"] == "delivered" and any(i.get("final_sale") for i in o["items"])
    )
    item = next(i for i in order["items"] if i.get("final_sale"))
    state = _state(order)
    result = handle_return_intake(state, f"I'd like to return my {item['name']} from {order['order_id']}")
    assert "final sale" in result["reply"].lower()
    assert "size exchange" in result["reply"].lower()
    assert result["reply"] != "This item is not eligible for return."
    assert "reason for returning" not in result["reply"].lower()
    assert state.return_intake is None


def test_non_returnable_category_explains_why_not_just_ineligible(orders):
    """A category-excluded item (e.g. jewellery) must explain the actual reason,
    not fall back to a generic 'not eligible' with no detail."""
    order = next(
        o for o in orders.values()
        if o["status"] == "delivered"
        and any(i.get("category") in {"jewellery", "innerwear"} for i in o["items"])
    )
    state = _state(order)
    handle_return_intake(state, f"I want to return {order['order_id']}")
    if state.return_intake and state.return_intake["stage"] == "item":
        item = next(i for i in order["items"] if i.get("category") in {"jewellery", "innerwear"})
        handle_return_intake(state, item["name"])
    result = handle_return_intake(state, "doesn't fit")
    assert result["reply"] != "This item is not eligible for return."
    assert "non-returnable" in result["reply"].lower()


def test_damage_claim_after_48_hours_is_ineligible(orders):
    older = next(o for o in orders.values() if o["status"] == "delivered" and o.get("delivered_at", "") < "2026-07-24")
    result = check_return_eligibility(older["order_id"], reason="damaged")
    assert result["eligible"] is False
    assert result["policy_reference"] == "§6.1"
