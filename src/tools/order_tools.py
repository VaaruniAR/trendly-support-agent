"""Order lookup tools — status in plain language with edge-case notes."""

from datetime import datetime

from src.config import REFERENCE_DATE, RETURN_WINDOW_DAYS, STATUS_LABELS
from src.data_loader import get_order_by_id, get_orders_by_email
from src.utils.dates import parse_iso


def _days_since_delivery(delivered_at: str | None, ref: str = REFERENCE_DATE) -> int | None:
    delivered = parse_iso(delivered_at)
    if not delivered:
        return None
    reference = datetime.fromisoformat(ref + "T00:00:00+05:30")
    return (reference.date() - delivered.date()).days


def _days_past_expected(expected_delivery: str | None, ref: str = REFERENCE_DATE) -> int | None:
    expected = parse_iso(expected_delivery)
    if not expected:
        return None
    reference = datetime.fromisoformat(ref + "T00:00:00+05:30")
    return (reference.date() - expected.date()).days


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def lookup_order(order_id: str, customer_email: str | None = None) -> dict:
    """Look up an order by ID. Optionally verify customer email for security."""
    order = get_order_by_id(order_id)
    if not order:
        return {
            "found": False,
            "error": f"No order found with ID {order_id.upper()}. Ask the customer to double-check the ID.",
        }

    if customer_email:
        if order["customer_email"].lower() != customer_email.strip().lower():
            return {
                "found": False,
                "error": "Email does not match this order. Do not disclose order details.",
                "security_note": "Verification failed — ask customer to confirm email on the account.",
            }

    days_since = _days_since_delivery(order.get("delivered_at"))
    summary = {
        "order_id": order["order_id"],
        "status": order["status"],
        "status_label": _status_label(order["status"]),
        "customer_name": order["customer_name"],
        "placed_at": order["placed_at"],
        "delivered_at": order.get("delivered_at"),
        "expected_delivery": order.get("expected_delivery"),
        "carrier": order.get("carrier"),
        "tracking_number": order.get("tracking_number"),
        "payment_method": order.get("payment_method"),
        "shipping_city": order.get("shipping_city"),
        "total_amount": order["total_amount"],
        "items": [
            {
                "item_id": i["item_id"],
                "sku": i["sku"],
                "name": i["name"],
                "size": i["size"],
                "price": i["price"],
                "category": i["category"],
                "final_sale": i.get("final_sale", False),
                "shipped": i.get("shipped"),
                "backorder_eta": i.get("backorder_eta"),
            }
            for i in order["items"]
        ],
    }

    status = order["status"]

    if status == "in_transit":
        summary["delivery_note"] = (
            "Your order is on its way. Metro delivery typically takes 2–4 business days; "
            "non-metro 4–7 business days (§1.2)."
        )
        if order.get("expected_delivery"):
            summary["expected_delivery"] = order["expected_delivery"]

    elif status == "partially_shipped":
        shipped = [i for i in order["items"] if i.get("shipped")]
        pending = [i for i in order["items"] if not i.get("shipped")]
        summary["delivery_note"] = (
            f"{len(shipped)} item(s) shipped; {len(pending)} item(s) on backorder. "
            "Remaining items ship at no extra cost when back in stock (§1.4)."
        )
        summary["shipped_items"] = [i["name"] for i in shipped]
        summary["pending_items"] = [
            {"name": i["name"], "backorder_eta": i.get("backorder_eta")} for i in pending
        ]

    elif status == "delayed":
        days_late = _days_past_expected(order.get("expected_delivery"))
        summary["delivery_note"] = (
            "This order is delayed — more than 3 business days past the expected delivery date (§1.5)."
        )
        if days_late is not None:
            summary["days_past_expected_delivery"] = days_late
        summary["policy_option"] = (
            "Customer may request a ₹250 store credit per §1.5. Do not offer unauthorized discounts."
        )
        summary["recommended_action"] = "Acknowledge the delay empathetically before quoting policy."

    elif status == "lost_in_transit":
        summary["alert"] = (
            "Carrier has marked this parcel as lost. This is a lost-parcel claim, NOT a return (§1.6)."
        )
        summary["recommended_action"] = (
            "Escalate to a human agent immediately. Do not process as a return. "
            "Human will offer free replacement or full refund within 5 business days."
        )
        summary["requires_escalation"] = True

    elif status == "cancelled":
        summary["cancellation"] = {
            "cancelled_at": order.get("cancelled_at"),
            "refund_status": order.get("refund_status"),
        }
        summary["delivery_note"] = (
            "This order was cancelled. Returns cannot be raised against cancelled orders (§2.6)."
        )

    elif status == "delivered" and days_since is not None:
        summary["days_since_delivery"] = days_since
        summary["return_window_days_remaining"] = max(0, RETURN_WINDOW_DAYS - days_since)

    if order.get("payment_method") == "cash_on_delivery":
        summary["cod_note"] = (
            "COD refunds require bank details collected by a human agent via secure link (§3.3). "
            "Never collect bank details in chat."
        )

    return {"found": True, "order": summary}


def list_customer_orders(customer_email: str) -> dict:
    """List all orders for a verified customer email."""
    orders = get_orders_by_email(customer_email)
    if not orders:
        return {
            "found": False,
            "message": "No orders found for this email.",
        }
    return {
        "found": True,
        "orders": [
            {
                "order_id": o["order_id"],
                "status": o["status"],
                "status_label": _status_label(o["status"]),
                "placed_at": o["placed_at"],
                "total_amount": o["total_amount"],
                "item_count": len(o["items"]),
            }
            for o in orders
        ],
    }
