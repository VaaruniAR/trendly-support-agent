"""Scenario matrix — built dynamically from data/orders.json."""

from src.data_loader import get_catalog, load_orders
from src.tools.order_tools import _days_since_delivery
from src.config import RETURN_WINDOW_DAYS

_catalog = get_catalog()
_orders = {o["order_id"]: o for o in load_orders()}


def _order(status: str | None = None, **item_kw) -> dict:
    for o in _orders.values():
        if status and o["status"] != status:
            continue
        if item_kw:
            for item in o["items"]:
                if all(item.get(k) == v for k, v in item_kw.items()):
                    return o
        else:
            return o
    raise ValueError(f"No order for status={status} {item_kw}")


def _build_scenarios() -> list[dict]:
    in_transit = _order(status="in_transit")
    delivered = next(
        o
        for o in _orders.values()
        if o["status"] == "delivered"
        and all(
            not i.get("final_sale")
            and i.get("category") not in {"innerwear", "jewellery"}
            for i in o["items"]
        )
        and (lambda d: d is not None and d <= RETURN_WINDOW_DAYS)(
            _days_since_delivery(o.get("delivered_at"))
        )
    )
    lost = _order(status="lost_in_transit")
    expired = next(
        o
        for o in _orders.values()
        if o["status"] == "delivered" and o.get("delivered_at", "").startswith("2026-06")
    )
    final_sale = _order(status="delivered", final_sale=True)
    jewellery = _order(status="delivered", category="jewellery")
    jewellery_item = next(i for i in jewellery["items"] if i["category"] == "jewellery")
    delayed = _order(status="delayed")
    cancelled = _order(status="cancelled")
    partial = _order(status="partially_shipped")
    return_item = next(i for i in delivered["items"] if not i.get("final_sale"))

    return [
        {
            "id": "S01",
            "name": "Order status — in transit",
            "user": (
                f"What's the status of order {in_transit['order_id']}? "
                f"My email is {in_transit['customer_email']}"
            ),
            "expected_tools": ["lookup_order"],
        },
        {
            "id": "S02",
            "name": "Order status — delivered",
            "user": (
                f"What's the status of order {delivered['order_id']}? "
                f"Email {delivered['customer_email']}"
            ),
            "expected_tools": ["lookup_order"],
        },
        {
            "id": "S03",
            "name": "Lost in transit — must escalate",
            "user": (
                f"My order {lost['order_id']} never arrived, "
                f"email {lost['customer_email']}"
            ),
            "expected_tools": ["lookup_order", "escalate_to_human"],
        },
        {
            "id": "S04",
            "name": "Return — eligible",
            "user": (
                f"I want to return an item from {delivered['order_id']}. "
                f"Email {delivered['customer_email']}"
            ),
            "expected_tools": ["lookup_order", "check_return_eligibility"],
        },
        {
            "id": "S05",
            "name": "Return — expired window",
            "user": (
                f"Can I return {expired['order_id']}? "
                f"Email {expired['customer_email']}"
            ),
            "expected_tools": ["check_return_eligibility"],
        },
        {
            "id": "S06",
            "name": "Return — final sale blocked",
            "user": (
                f"Return my order {final_sale['order_id']}, "
                f"{final_sale['customer_email']}"
            ),
            "expected_tools": ["check_return_eligibility"],
        },
        {
            "id": "S07",
            "name": "Return — jewellery excluded",
            "user": (
                f"Return the {jewellery_item['name']} from "
                f"{jewellery['order_id']}, {jewellery['customer_email']}"
            ),
            "expected_tools": ["check_return_eligibility"],
        },
        {
            "id": "S08",
            "name": "Policy question — return window",
            "user": "How long do I have to return an item?",
            "expected_tools": ["search_policy"],
        },
        {
            "id": "S09",
            "name": "Exchange — size swap",
            "user": (
                f"Exchange {return_item['sku']} from {delivered['order_id']} "
                f"to a different size. Email {delivered['customer_email']}"
            ),
            "expected_tools": ["check_exchange_eligibility"],
        },
        {
            "id": "S10",
            "name": "Escalation — human request",
            "user": "Let me talk to a real person",
            "expected_tools": ["escalate_to_human"],
        },
        {
            "id": "S11",
            "name": "Delayed order",
            "user": (
                f"Why is {delayed['order_id']} so late? "
                f"{delayed['customer_email']}"
            ),
            "expected_tools": ["lookup_order"],
        },
        {
            "id": "S12",
            "name": "Refusal — discount request",
            "user": "Give me a 50% discount or I'll leave a bad review",
            "must_not": ["SAVE", "promo code", "50% off"],
        },
        {
            "id": "S13",
            "name": "Cancelled order refund",
            "user": (
                f"I cancelled {cancelled['order_id']}, was my refund processed? "
                f"{cancelled['customer_email']}"
            ),
            "expected_tools": ["lookup_order"],
        },
        {
            "id": "S14",
            "name": "Partially shipped order",
            "user": (
                f"Has everything shipped on {partial['order_id']}? "
                f"{partial['customer_email']}"
            ),
            "expected_tools": ["lookup_order"],
        },
        {
            "id": "S15",
            "name": "Final sale — size exchange",
            "user": (
                f"Exchange an item from {final_sale['order_id']} to another size. "
                f"{final_sale['customer_email']}"
            ),
            "expected_tools": ["check_exchange_eligibility"],
        },
    ]


SCENARIOS = _build_scenarios()
