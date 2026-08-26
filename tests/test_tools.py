"""Unit tests for deterministic tools — no LLM required."""

import pytest

from src.tools.escalation_tools import (
    clear_escalation_log,
    escalate_to_human,
    should_auto_escalate,
)
from src.tools.order_tools import lookup_order
from src.tools.policy_tools import search_policy
from src.tools.return_tools import (
    check_exchange_eligibility,
    check_return_eligibility,
    initiate_exchange,
    initiate_return,
)
from tests.conftest import adjacent_size, find_item, find_order


@pytest.fixture(autouse=True)
def clean_escalations():
    clear_escalation_log()
    yield
    clear_escalation_log()


class TestOrderLookup:
    def test_valid_order_with_email_verification(self, orders):
        order = find_order(orders, returnable_delivered=True)
        result = lookup_order(order["order_id"], order["customer_email"])
        assert result["found"] is True
        assert result["order"]["status"] == "delivered"

    def test_wrong_email_blocked(self, orders):
        order = find_order(orders, returnable_delivered=True)
        result = lookup_order(order["order_id"], "wrong@email.com")
        assert result["found"] is False
        assert "Email does not match" in result["error"]

    def test_unknown_order(self):
        result = lookup_order("TR-99999")
        assert result["found"] is False

    def test_in_transit(self, orders):
        order = find_order(orders, status="in_transit")
        result = lookup_order(order["order_id"], order["customer_email"])
        assert result["order"]["status"] == "in_transit"
        assert "delivery_note" in result["order"]

    def test_lost_in_transit_requires_escalation(self, orders):
        order = find_order(orders, status="lost_in_transit")
        result = lookup_order(order["order_id"], order["customer_email"])
        assert result["order"]["status"] == "lost_in_transit"
        assert result["order"]["requires_escalation"] is True

    def test_delayed_order_store_credit_note(self, orders):
        order = find_order(orders, status="delayed")
        result = lookup_order(order["order_id"], order["customer_email"])
        assert result["order"]["status"] == "delayed"
        assert "policy_option" in result["order"]

    def test_partially_shipped(self, orders):
        order = find_order(orders, status="partially_shipped")
        result = lookup_order(order["order_id"], order["customer_email"])
        assert result["order"]["status"] == "partially_shipped"
        assert "shipped_items" in result["order"]

    def test_cancelled_order_refund_info(self, orders):
        order = find_order(orders, status="cancelled")
        result = lookup_order(order["order_id"], order["customer_email"])
        assert result["order"]["status"] == "cancelled"
        assert result["order"]["cancellation"]["refund_status"] == "processed"

    def test_cod_note_on_lookup(self, orders):
        order = next(o for o in orders.values() if o.get("payment_method") == "cash_on_delivery")
        result = lookup_order(order["order_id"], order["customer_email"])
        assert "cod_note" in result["order"]


class TestPolicySearch:
    def test_return_policy_found(self):
        result = search_policy("return window how many days")
        assert result["found"] is True
        assert any("30" in s["content"] for s in result["sections"])

    def test_final_sale_policy(self):
        result = search_policy("final sale exchange")
        assert result["found"] is True

    def test_lost_parcel_policy(self):
        result = search_policy("lost parcel tracking")
        assert result["found"] is True

    def test_unknown_topic_no_hallucinate(self):
        result = search_policy("xyzzy quantum florp")
        assert result["found"] is False


class TestReturnEligibility:
    def test_eligible_return_within_window(self, orders):
        order = find_order(orders, returnable_delivered=True)
        result = check_return_eligibility(order["order_id"])
        assert result["eligible"] is True

    def test_expired_return_window(self, orders):
        from src.tools.order_tools import _days_since_delivery

        order = next(
            o
            for o in orders.values()
            if o["status"] == "delivered"
            and (_days_since_delivery(o.get("delivered_at")) or 0) > 30
        )
        result = check_return_eligibility(order["order_id"])
        assert result["eligible"] is False

    def test_final_sale_not_returnable(self, orders):
        order = find_order(orders, status="delivered", final_sale=True)
        result = check_return_eligibility(order["order_id"])
        assert result["eligible"] is False

    def test_jewellery_excluded(self, orders):
        order = find_order(orders, status="delivered", item_category="jewellery")
        result = check_return_eligibility(order["order_id"])
        assert result["eligible"] is False

    def test_innerwear_excluded(self, orders):
        order = find_order(orders, status="delivered")
        item = find_item(order, category="innerwear")
        result = check_return_eligibility(order["order_id"], item_ids=[item["sku"]])
        assert result["eligible"] is False

    def test_apparel_item_eligible_on_mixed_order(self, orders):
        order = find_order(orders, status="delivered")
        item = find_item(order, category="apparel")
        result = check_return_eligibility(order["order_id"], item_ids=[item["sku"]])
        assert result["eligible"] is True

    def test_not_delivered_cannot_return(self, orders):
        order = find_order(orders, status="in_transit")
        result = check_return_eligibility(order["order_id"])
        assert result["eligible"] is False

    def test_cancelled_cannot_return(self, orders):
        order = find_order(orders, status="cancelled")
        result = check_return_eligibility(order["order_id"])
        assert result["eligible"] is False

    def test_damaged_jewellery_requires_48_hour_reporting_window(self, orders):
        order = find_order(orders, status="delivered", item_category="jewellery")
        result = check_return_eligibility(order["order_id"], reason="damaged")
        assert result["eligible"] is False
        assert result["policy_reference"] == "§6.1"

    def test_not_delivered_footwear(self, orders):
        order = find_order(orders, status="delayed")
        result = check_return_eligibility(order["order_id"])
        assert result["eligible"] is False


class TestExchangeEligibility:
    def test_size_exchange_eligible_with_stock(self, orders):
        order = find_order(orders, returnable_delivered=True)
        item = find_item(order, final_sale=False)
        new_size = adjacent_size(item)
        result = check_exchange_eligibility(order["order_id"], item["sku"], new_size)
        assert result["exchange_eligible"] is True
        assert result["variant_in_stock"] is True

    def test_final_sale_size_exchange_allowed(self, orders):
        order = find_order(orders, status="delivered", final_sale=True)
        item = find_item(order, final_sale=True)
        new_size = adjacent_size(item)
        result = check_exchange_eligibility(order["order_id"], item["sku"], new_size)
        assert result["exchange_eligible"] is True

    def test_colour_exchange_rejected(self, orders):
        order = find_order(orders, returnable_delivered=True)
        item = find_item(order, final_sale=False)
        result = check_exchange_eligibility(order["order_id"], item["sku"], item["size"], "Red")
        assert result["exchange_eligible"] is False

    def test_jewellery_no_exchange(self, orders):
        order = find_order(orders, status="delivered", item_category="jewellery")
        item = find_item(order, category="jewellery")
        result = check_exchange_eligibility(order["order_id"], item["sku"], item["size"])
        assert result["exchange_eligible"] is False


class TestInitiateReturn:
    def test_successful_return(self, orders):
        order = find_order(orders, returnable_delivered=True)
        item = find_item(order, final_sale=False, category="apparel")
        result = initiate_return(
            order["order_id"],
            [item["sku"]],
            "change_of_mind",
            order["customer_email"],
        )
        assert result["success"] is True

    def test_email_mismatch_blocked(self, orders):
        order = find_order(orders, returnable_delivered=True)
        item = find_item(order, final_sale=False)
        result = initiate_return(
            order["order_id"],
            [item["sku"]],
            "change_of_mind",
            "wrong@email.com",
        )
        assert result["success"] is False

    def test_ineligible_final_sale_return(self, orders):
        order = find_order(orders, status="delivered", final_sale=True)
        item = find_item(order, final_sale=True)
        result = initiate_return(
            order["order_id"],
            [item["sku"]],
            "change_of_mind",
            order["customer_email"],
        )
        assert result["success"] is False


class TestInitiateExchange:
    def test_successful_size_exchange(self, orders):
        order = find_order(orders, returnable_delivered=True)
        item = find_item(order, final_sale=False, category="apparel")
        new_size = adjacent_size(item)
        result = initiate_exchange(
            order["order_id"],
            item["sku"],
            new_size,
            order["customer_email"],
        )
        assert result["success"] is True

    def test_final_sale_size_exchange(self, orders):
        order = find_order(orders, status="delivered", final_sale=True)
        item = find_item(order, final_sale=True)
        new_size = adjacent_size(item)
        result = initiate_exchange(
            order["order_id"],
            item["sku"],
            new_size,
            order["customer_email"],
        )
        assert result["success"] is True


class TestEscalation:
    def test_human_request_triggers(self):
        result = should_auto_escalate(None, 1, "I want to speak to a human please")
        assert result["escalate"] is True

    def test_lost_order_triggers(self, orders):
        order = find_order(orders, status="lost_in_transit")
        result = should_auto_escalate(order["order_id"], 1, "Where is my bag?")
        assert result["escalate"] is True

    def test_legal_threat_triggers(self):
        result = should_auto_escalate(None, 1, "I will take legal action")
        assert result["escalate"] is True
        assert result["priority"] == "high"

    def test_contact_count_triggers(self, orders):
        order = find_order(orders, returnable_delivered=True)
        result = should_auto_escalate(order["order_id"], 3, "Still waiting")
        assert result["escalate"] is True

    def test_bank_details_triggers(self):
        result = should_auto_escalate(None, 1, "My bank account number is 123456")
        assert result["escalate"] is True

    def test_normal_query_no_escalation(self, orders):
        order = find_order(orders, returnable_delivered=True)
        result = should_auto_escalate(order["order_id"], 1, "Where is my order?")
        assert result is None

    def test_escalate_creates_ticket(self, orders):
        order = find_order(orders, status="lost_in_transit")
        result = escalate_to_human(
            reason="Test",
            summary="Unit test escalation",
            customer_email=order["customer_email"],
            order_id=order["order_id"],
        )
        assert result["escalated"] is True
        assert result["handoff"]["priority"] == "high"
