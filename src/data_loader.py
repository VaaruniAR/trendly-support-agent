"""
Data loader — reads orders.json and trendly_policy.md.

All order lookups go through this module so the rest of the app
never hardcodes order IDs or customer emails.
"""
import json
from functools import lru_cache
from typing import Any

from src.config import ORDERS_PATH, POLICY_PATH, STATUS_LABELS

# Generic size ladders for simulated exchange stock (not order-specific)
LETTER_SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
WAIST_SIZES = ["26", "28", "30", "32", "34", "36", "38"]
SHOE_SIZES = ["39", "40", "41", "42", "43", "44", "45"]
FREE_SIZES = ["FS", "Free Size"]

def _normalize_item(raw: dict) -> dict[str, Any]:
    """Map JSON item fields to the internal shape tools expect (sku doubles as item_id)."""
    return {
        "item_id": raw["sku"],
        "sku": raw["sku"],
        "name": raw["name"],
        "size": raw["size"],
        "category": raw["category"],
        "price": raw["price"],
        "qty": raw.get("qty", 1),
        "final_sale": raw.get("final_sale", False),
        "shipped": raw.get("shipped"),
        "backorder_eta": raw.get("backorder_eta"),
    }


def _normalize_order(raw: dict[str, Any], customers: dict[str, dict]) -> dict[str, Any]:
    """Join order row with customer record and flatten item list."""
    customer = customers.get(raw["customer_id"], {})
    order: dict[str, Any] = {
        "order_id": raw["order_id"],
        "customer_id": raw["customer_id"],
        "customer_email": customer.get("email", ""),
        "customer_name": customer.get("name", ""),
        "status": raw["status"],
        "placed_at": raw["placed_at"],
        "delivered_at": raw.get("delivered_at"),
        "expected_delivery": raw.get("expected_delivery"),
        "carrier": raw.get("carrier"),
        "tracking_number": raw.get("tracking_number"),
        "payment_method": raw.get("payment_method"),
        "shipping_city": raw.get("shipping_city"),
        "total_amount": raw["total"],
        "items": [_normalize_item(i) for i in raw["items"]],
        "cancelled_at": raw.get("cancelled_at"),
        "refund_status": raw.get("refund_status"),
    }
    if raw.get("_note_for_designers"):
        order["designer_note"] = raw["_note_for_designers"]
    return order


@lru_cache(maxsize=1)
def load_policy() -> str:
    """Cached read of trendly_policy.md — used by search_policy tool."""
    return POLICY_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_raw_data() -> dict[str, Any]:
    """Parse orders.json once; customers + orders arrays live in the same file."""
    with ORDERS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_orders() -> list[dict[str, Any]]:
    raw = _load_raw_data()
    customers = {c["customer_id"]: c for c in raw.get("customers", [])}
    return [_normalize_order(o, customers) for o in raw.get("orders", [])]


@lru_cache(maxsize=1)
def _order_index() -> dict[str, dict[str, Any]]:
    return {order["order_id"].upper(): order for order in load_orders()}


@lru_cache(maxsize=1)
def _orders_by_email() -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for order in load_orders():
        email = order["customer_email"].lower()
        index.setdefault(email, []).append(order)
    return index


def get_order_by_id(order_id: str) -> dict[str, Any] | None:
    """Case-insensitive order lookup — agent may pass tr-4521 or TR-4521."""
    return _order_index().get(order_id.strip().upper())


def get_orders_by_email(email: str) -> list[dict[str, Any]]:
    return list(_orders_by_email().get(email.strip().lower(), []))


def _size_ladder(current_size: str, category: str) -> list[str]:
    """Pick the right size scale (letters, waist, shoes) for exchange simulation."""
    if current_size in FREE_SIZES:
        return FREE_SIZES
    if category == "footwear" or (current_size.isdigit() and int(current_size) >= 35):
        return SHOE_SIZES
    if current_size.isdigit():
        return WAIST_SIZES
    return LETTER_SIZES


def get_available_exchange_sizes(sku: str, current_size: str, category: str) -> list[str]:
    """
    Exchange sizes derived from orders.json catalog + adjacent sizes on a generic ladder.
    Simulates WMS stock without hardcoding per-SKU inventory.
    """
    seen: set[str] = set()
    for order in load_orders():
        for item in order["items"]:
            if item["sku"].upper() == sku.upper():
                seen.add(item["size"])

    ladder = _size_ladder(current_size, category)
    available = set(seen)
    # Also offer adjacent sizes on the ladder (simulates warehouse having neighbors in stock)
    if current_size in ladder:
        idx = ladder.index(current_size)
        for adj in (idx - 1, idx + 1):
            if 0 <= adj < len(ladder):
                available.add(ladder[adj])
    available.discard(current_size)
    return sorted(available, key=lambda s: ladder.index(s) if s in ladder else len(ladder))


def _order_summary(order: dict[str, Any]) -> dict[str, Any]:
    """Customer-safe order card for GET /catalog.

    This deliberately includes the item fields needed to recognise an order in
    the UI (name, size, quantity, price, fulfilment state), while excluding the
    customer email/name and internal designer annotation. The client already
    has an authenticated storefront identity; it must not receive a directory
    of customer data as a side effect of rendering an order card.
    """
    status = order["status"]
    return {
        "order_id": order["order_id"],
        "status": status,
        "status_label": STATUS_LABELS.get(status, status.replace("_", " ").title()),
        "total_amount": order["total_amount"],
        "item_count": len(order["items"]),
        "placed_at": order["placed_at"],
        "delivered_at": order.get("delivered_at"),
        "expected_delivery": order.get("expected_delivery"),
        "carrier": order.get("carrier"),
        "tracking_number": order.get("tracking_number"),
        "payment_method": order.get("payment_method"),
        "items": [
            {
                "sku": i["sku"],
                "name": i["name"],
                "size": i["size"],
                "category": i["category"],
                "qty": i["qty"],
                "price": i["price"],
                "final_sale": i.get("final_sale", False),
                "shipped": i.get("shipped"),
                "backorder_eta": i.get("backorder_eta"),
            }
            for i in order["items"]
        ],
    }


# Generic starter prompts for the UI sidebar — user fills in order ID / email before sending
QUICK_SCENARIOS: list[dict[str, Any]] = [
    {"label": "Order status", "message": "What's the status of my order? My order ID is ", "needs_order": True},
    {"label": "Start a return", "message": "I'd like to start a return. My order ID is ", "needs_order": True},
    {"label": "Lost parcel", "message": "My order never arrived. Order ID: ", "needs_order": True},
    {"label": "Final Sale refund", "message": "I want a refund for a Final Sale item. Order ID: ", "needs_order": True},
    {"label": "Return policy", "message": "How long do I have to return an item?", "needs_order": False},
    {"label": "Speak to human", "message": "I'd like to speak to a human agent please.", "needs_order": False},
]


def get_customers() -> list[dict[str, Any]]:
    """Customer directory for the UI's account switcher — id, name, email, order count."""
    raw = _load_raw_data()
    counts: dict[str, int] = {}
    for order in load_orders():
        counts[order["customer_id"]] = counts.get(order["customer_id"], 0) + 1
    return [
        {
            "customer_id": c["customer_id"],
            "name": c["name"],
            "email": c["email"],
            "order_count": counts.get(c["customer_id"], 0),
        }
        for c in raw.get("customers", [])
    ]


def get_catalog(customer_email: str | None = None) -> dict[str, Any]:
    """
    Payload for GET /catalog — powers demo scenarios and order hints in the UI.

    Orders are scoped to the signed-in customer: no email, no orders. Each customer
    should only ever see their own order history, same as a real storefront account.
    """
    orders = get_orders_by_email(customer_email) if customer_email else []
    return {
        "orders": [_order_summary(o) for o in orders],
        "scenarios": QUICK_SCENARIOS,
    }


def clear_data_cache() -> None:
    """Clear cached data (useful in tests)."""
    load_policy.cache_clear()
    _load_raw_data.cache_clear()
    load_orders.cache_clear()
    _order_index.cache_clear()
    _orders_by_email.cache_clear()
