"""Return-tools regression tests — refund messaging must match §3.1 exactly
per the customer's actual payment method, not a hard-coded card-only line."""

from tests.conftest import find_order
from src.tools.return_tools import REFUND_DESTINATIONS, _refund_timeline_note, initiate_return


def test_refund_timeline_matches_policy_table_for_every_payment_method():
    """§3.1: card 5–7 business days to the card; UPI 3–5 days to the UPI ID;
    COD 7–10 days via bank transfer/store credit; store credit is immediate."""
    assert "5–7 business days" in _refund_timeline_note("credit_card")
    assert "your original card" in _refund_timeline_note("credit_card")
    assert "5–7 business days" in _refund_timeline_note("debit_card")
    assert "5–7 business days" in _refund_timeline_note("prepaid_card")

    upi_note = _refund_timeline_note("upi")
    assert "3–5 business days" in upi_note
    assert "UPI ID" in upi_note

    cod_note = _refund_timeline_note("cash_on_delivery")
    assert "7–10 business days" in cod_note
    assert "bank transfer" in cod_note.lower() or "store credit" in cod_note.lower()
    assert "card payments" not in cod_note.lower()

    credit_note = _refund_timeline_note("store_credit")
    assert "immediately" in credit_note.lower()

    # An unrecognized/missing payment method must not silently claim UPI's or
    # COD's timeline — it falls back to the (safer, slower) card row.
    assert _refund_timeline_note(None) == _refund_timeline_note("credit_card")
    assert _refund_timeline_note("something_new") == _refund_timeline_note("credit_card")


def test_initiate_return_message_reflects_actual_payment_method(orders, monkeypatch):
    """Regression: the return-confirmation message used to hard-code
    'Refund in 5–7 business days ... for card payments' regardless of how the
    order was actually paid — wrong for UPI (3–5 days) and misleading for COD
    (which also needs the separate §3.3 bank-detail escalation, not a card
    refund promise). Each payment method's confirmation must match its own
    §3.1 row."""
    order = find_order(orders, returnable_delivered=True)
    item_ids = [i["item_id"] for i in order["items"]]

    for payment_method, (destination_phrase, window) in REFUND_DESTINATIONS.items():
        monkeypatch.setitem(order, "payment_method", payment_method)
        result = initiate_return(order["order_id"], item_ids, "change_of_mind", order["customer_email"])
        assert result["success"] is True
        assert destination_phrase in result["message"]
        if window:
            assert window in result["message"]
        assert "for card payments" not in result["message"]

    # COD keeps the bank-detail escalation note on top of its own refund line.
    monkeypatch.setitem(order, "payment_method", "cash_on_delivery")
    result = initiate_return(order["order_id"], item_ids, "change_of_mind", order["customer_email"])
    assert result["cod_escalation_required"] is True
    assert "secure bank detail collection" in result["message"]
    assert "via bank transfer or store credit" in result["message"]
