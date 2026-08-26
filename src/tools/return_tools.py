"""Return and exchange tools — deterministic eligibility from order + policy rules."""
from datetime import datetime

from src.config import EXCLUDED_CATEGORIES, RETURN_WINDOW_DAYS
from src.data_loader import get_available_exchange_sizes, get_order_by_id
from src.tools.order_tools import _days_since_delivery

DAMAGE_REASONS = {"damaged", "wrong_item", "defective"}


def _category_excluded(category: str) -> bool:
    return category.lower().strip() in EXCLUDED_CATEGORIES


def _item_eligibility_issues(
    item: dict,
    reason: str,
    *,
    for_exchange: bool = False,
) -> list[str]:
    issues: list[str] = []
    category = item.get("category", "")

    if item.get("final_sale"):
        if for_exchange:
            issues.append(
                "Final Sale item — size exchange only, no refund or store credit (§2.4)"
            )
        else:
            issues.append(
                "Final Sale item — not eligible for refund. Size exchange only (§2.4)"
            )
        return issues

    if _category_excluded(category) and reason not in DAMAGE_REASONS:
        issues.append(f"Category '{category}' is non-returnable (§2.3)")
        if not for_exchange:
            issues.append(
                "Exception: damaged/wrong/defective items may qualify under §6.2 — verify reason."
            )

    if category.lower() == "footwear" and reason == "change_of_mind":
        issues.append(
            "Footwear returns require original shoe box; ₹300 deduction without box (§2.5)"
        )

    return issues


def check_return_eligibility(
    order_id: str,
    item_ids: list[str] | None = None,
    reason: str = "change_of_mind",
) -> dict:
    """
    Deterministic eligibility check combining order data with policy rules.
    Does NOT initiate a return — use initiate_return after customer confirms.
    """
    order = get_order_by_id(order_id)
    if not order:
        return {"eligible": False, "error": f"Order {order_id} not found."}

    if order["status"] == "cancelled":
        return {
            "eligible": False,
            "reason": "Order is cancelled. Returns cannot be raised against cancelled orders.",
            "policy_reference": "§2.6",
        }

    if order["status"] != "delivered":
        return {
            "eligible": False,
            "reason": (
                f"Order status is '{order['status']}'. Returns require delivered status."
            ),
            "policy_reference": "§2.1",
        }

    days_since = _days_since_delivery(order.get("delivered_at"))
    if days_since is None:
        return {"eligible": False, "reason": "Delivery date unavailable."}

    if days_since > RETURN_WINDOW_DAYS:
        return {
            "eligible": False,
            "reason": (
                f"Return window expired. Delivered {days_since} days ago "
                f"(limit: {RETURN_WINDOW_DAYS} days)."
            ),
            "policy_reference": "§2.1",
            "days_since_delivery": days_since,
        }

    if reason in DAMAGE_REASONS and days_since > 2:
        return {
            "eligible": False,
            "reason": (
                f"Damaged, defective, and incorrect-item claims must be reported within 48 hours "
                f"of delivery. This order was delivered {days_since} days ago."
            ),
            "policy_reference": "§6.1",
            "days_since_delivery": days_since,
        }

    target_items = order["items"]
    if item_ids:
        ids = {i.upper() for i in item_ids}
        target_items = [i for i in order["items"] if i["item_id"].upper() in ids]
        if not target_items:
            return {"eligible": False, "reason": "Specified item IDs not found on this order."}

    item_results = []
    all_eligible = True

    for item in target_items:
        issues = _item_eligibility_issues(item, reason, for_exchange=False)

        if item.get("final_sale"):
            eligible = False
        elif _category_excluded(item.get("category", "")) and reason not in DAMAGE_REASONS:
            eligible = False
        else:
            eligible = True

        if not eligible:
            all_eligible = False

        item_results.append(
            {
                "item_id": item["item_id"],
                "name": item["name"],
                "eligible": eligible,
                "issues": issues,
                "exchange_only": item.get("final_sale", False),
            }
        )

    refund_note = None
    if reason in DAMAGE_REASONS:
        refund_note = "Full refund including shipping per §3.2 and §6.2."
    elif reason == "change_of_mind":
        refund_note = "Original ₹99 shipping fee is not refunded for change-of-mind returns (§3.2)."

    cod_note = None
    if order.get("payment_method") == "cash_on_delivery" and all_eligible:
        cod_note = (
            "COD refund requires bank details via human agent secure link (§3.3). Escalate for collection."
        )

    return {
        "eligible": all_eligible,
        "order_id": order["order_id"],
        "days_since_delivery": days_since,
        "days_remaining_in_window": RETURN_WINDOW_DAYS - days_since,
        "items": item_results,
        "refund_note": refund_note,
        "cod_note": cod_note,
        "policy_reference": "§2.1",
    }


def check_exchange_eligibility(
    order_id: str,
    item_id: str,
    desired_size: str | None = None,
    desired_color: str | None = None,
) -> dict:
    """Check if a size exchange is eligible for a specific item (size only per §4.1)."""
    order = get_order_by_id(order_id)
    if not order:
        return {"exchange_eligible": False, "error": f"Order {order_id} not found."}

    if order["status"] == "cancelled":
        return {
            "exchange_eligible": False,
            "reason": "Cancelled orders cannot be exchanged.",
            "policy_reference": "§2.6",
        }

    if order["status"] != "delivered":
        return {
            "exchange_eligible": False,
            "reason": f"Order must be delivered. Current status: {order['status']}.",
            "policy_reference": "§4.2",
        }

    days_since = _days_since_delivery(order.get("delivered_at"))
    if days_since is None:
        return {"exchange_eligible": False, "reason": "Delivery date unavailable."}

    if days_since > RETURN_WINDOW_DAYS:
        return {
            "exchange_eligible": False,
            "reason": f"Exchange window expired ({days_since} days since delivery).",
            "policy_reference": "§4.2",
        }

    item = next(
        (i for i in order["items"] if i["item_id"].upper() == item_id.upper()),
        None,
    )
    if not item:
        return {"exchange_eligible": False, "reason": "Item not found on this order."}

    if desired_color:
        return {
            "exchange_eligible": False,
            "reason": (
                "Trendly offers size exchanges only — not colour or style changes (§4.1). "
                "Customer should return and place a new order to change colour/style."
            ),
            "policy_reference": "§4.1",
        }

    issues = _item_eligibility_issues(item, "exchange", for_exchange=True)
    if _category_excluded(item.get("category", "")):
        return {
            "exchange_eligible": False,
            "reason": f"Category '{item['category']}' cannot be exchanged (§2.3).",
            "issues": issues,
            "policy_reference": "§2.3",
        }

    if not desired_size:
        return {
            "exchange_eligible": True,
            "message": "Item may be eligible for size exchange. Ask customer for desired size.",
            "current_size": item["size"],
            "final_sale": item.get("final_sale", False),
            "policy_reference": "§4.1",
            "note": (
                "Size exchanges only. Final Sale items: size exchange only, no refund (§2.4)."
                if item.get("final_sale")
                else "Size exchanges only per §4.1."
            ),
        }

    if desired_size == item["size"]:
        return {
            "exchange_eligible": False,
            "reason": "Requested size is the same as current size.",
        }

    available_sizes = get_available_exchange_sizes(
        item["sku"], item["size"], item.get("category", "apparel")
    )
    in_stock = desired_size in available_sizes

    return {
        "exchange_eligible": True,
        "variant_in_stock": in_stock,
        "requested_size": desired_size,
        "current_size": item["size"],
        "available_sizes": available_sizes,
        "final_sale": item.get("final_sale", False),
        "policy_reference": "§4.3" if not in_stock else "§4.1",
        "note": (
            "If requested size unavailable, exchange converts to refund under §3 (§4.3)."
            if not in_stock
            else "Free reverse pickup for size exchange (§5.1)."
        ),
    }


def initiate_return(
    order_id: str,
    item_ids: list[str],
    reason: str,
    customer_email: str,
) -> dict:
    """Initiate a return after eligibility is confirmed and customer verified."""
    order = get_order_by_id(order_id)
    if not order:
        return {"success": False, "error": "Order not found."}

    if order["customer_email"].lower() != customer_email.strip().lower():
        return {"success": False, "error": "Email verification failed."}

    eligibility = check_return_eligibility(order_id, item_ids=item_ids, reason=reason)
    if not eligibility.get("eligible"):
        return {
            "success": False,
            "error": "Return not eligible.",
            "eligibility": eligibility,
        }

    return_id = f"RET-{order_id.split('-')[1]}{datetime.now().strftime('%H%M')}"
    result = {
        "success": True,
        "return_id": return_id,
        "order_id": order_id,
        "item_ids": item_ids,
        "reason": reason,
        "status": "Pickup Scheduled",
        "message": (
            "Return pickup scheduled. Carrier will attempt pickup up to 2 times (§5.1). "
            "Refund in 5–7 business days after warehouse inspection for card payments (§3.1)."
        ),
        "refund_note": eligibility.get("refund_note"),
    }

    if order.get("payment_method") == "cash_on_delivery":
        result["cod_escalation_required"] = True
        result["message"] += (
            " COD refund: escalate to human agent for secure bank detail collection (§3.3)."
        )

    return result


def initiate_exchange(
    order_id: str,
    item_id: str,
    desired_size: str,
    customer_email: str,
    desired_color: str | None = None,
) -> dict:
    """Initiate a size exchange after eligibility and stock check."""
    order = get_order_by_id(order_id)
    if not order:
        return {"success": False, "error": "Order not found."}

    if order["customer_email"].lower() != customer_email.strip().lower():
        return {"success": False, "error": "Email verification failed."}

    exchange_check = check_exchange_eligibility(
        order_id, item_id, desired_size, desired_color
    )
    if not exchange_check.get("exchange_eligible"):
        return {"success": False, "error": "Not eligible for exchange.", "details": exchange_check}

    if desired_color:
        return {
            "success": False,
            "error": "Only size exchanges are supported (§4.1).",
            "details": exchange_check,
        }

    if not exchange_check.get("variant_in_stock"):
        return {
            "success": False,
            "error": "Requested size unavailable.",
            "options": [
                "Convert to full refund under §3 per §4.3",
                "Customer may choose refund destination per §3.1",
            ],
            "details": exchange_check,
        }

    exchange_id = f"EXC-{order_id.split('-')[1]}{datetime.now().strftime('%H%M')}"
    return {
        "success": True,
        "exchange_id": exchange_id,
        "order_id": order_id,
        "item_id": item_id,
        "new_size": desired_size,
        "status": "Awaiting Pickup",
        "message": (
            "Size exchange initiated. Free reverse pickup scheduled (§5.1). "
            "Replacement ships after original item is received (§4.3)."
        ),
    }
