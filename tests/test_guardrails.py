"""Guardrail and response validation tests."""

from src.guardrails.validators import (
    contains_forbidden_promise,
    contains_unauthorized_discount,
    sanitize_response,
)


class TestGuardrails:
    def test_blocks_discount_offer(self):
        assert contains_unauthorized_discount("Here's a 20% off promo code: SAVE20")

    def test_blocks_goodwill_credit(self):
        assert contains_unauthorized_discount("I'll offer goodwill store credit")

    def test_allows_policy_delayed_store_credit(self):
        assert not contains_unauthorized_discount(
            "As your order is delayed, you qualify for a ₹250 store credit per our policy."
        )

    def test_allows_normal_response(self):
        assert not contains_unauthorized_discount("Your return is eligible within 30 days.")

    def test_sanitize_strips_discount_language(self):
        text = "Sure! Here's a discount code SAVE50 for you."
        cleaned, warnings = sanitize_response(text)
        assert "unauthorized_discount" in warnings

    def test_blocks_impossible_refund_promise(self):
        assert contains_forbidden_promise("Your refund within 1 business days is guaranteed.")
