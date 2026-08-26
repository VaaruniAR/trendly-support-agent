"""Exact-fact regression checks for the supplied orders dataset."""

import json

from src.config import ORDERS_PATH
from src.data_loader import get_catalog, load_orders


def _source():
    payload = json.loads(ORDERS_PATH.read_text(encoding="utf-8"))
    customers = {customer["customer_id"]: customer for customer in payload["customers"]}
    orders = {order["order_id"]: order for order in payload["orders"]}
    return customers, orders


def test_all_ten_orders_and_every_order_fact_match_orders_json():
    customers, source_orders = _source()
    loaded = {order["order_id"]: order for order in load_orders()}

    assert len(source_orders) == 10
    assert loaded.keys() == source_orders.keys()
    for order_id, source in source_orders.items():
        actual = loaded[order_id]
        assert actual["customer_id"] == source["customer_id"]
        assert actual["customer_email"] == customers[source["customer_id"]]["email"]
        assert actual["total_amount"] == source["total"]
        for key in ("status", "placed_at", "delivered_at", "expected_delivery", "carrier", "tracking_number", "payment_method", "shipping_city", "cancelled_at", "refund_status"):
            assert actual.get(key) == source.get(key)
        assert len(actual["items"]) == len(source["items"])
        for actual_item, source_item in zip(actual["items"], source["items"], strict=True):
            for key in ("sku", "name", "size", "category", "price"):
                assert actual_item[key] == source_item[key]
            assert actual_item["qty"] == source_item.get("qty", 1)
            assert actual_item["final_sale"] == source_item.get("final_sale", False)
            assert actual_item.get("shipped") == source_item.get("shipped")
            assert actual_item.get("backorder_eta") == source_item.get("backorder_eta")


def test_customer_catalogs_are_scoped_and_preserve_ui_order_facts():
    customers, source_orders = _source()
    for customer in customers.values():
        cards = get_catalog(customer["email"])["orders"]
        expected = [o for o in source_orders.values() if o["customer_id"] == customer["customer_id"]]
        assert {card["order_id"] for card in cards} == {o["order_id"] for o in expected}
        for card in cards:
            source = source_orders[card["order_id"]]
            assert card["total_amount"] == source["total"]
            for key in ("status", "placed_at", "delivered_at", "expected_delivery", "carrier", "tracking_number", "payment_method"):
                assert card.get(key) == source.get(key)
            assert "customer_email" not in card and "customer_name" not in card
            for actual_item, source_item in zip(card["items"], source["items"], strict=True):
                assert actual_item["sku"] == source_item["sku"]
                for key in ("name", "size", "category", "price"):
                    assert actual_item[key] == source_item[key]
                assert actual_item["qty"] == source_item.get("qty", 1)
