"""End-to-end tests: API layer + agent orchestration with mocked LLM."""

import json
import re
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.agent.orchestrator import SupportAgent
from src.agent.state import ConversationState, session_store
from src.data_loader import load_orders
from src.main import app
from src.tools.escalation_tools import clear_escalation_log
from tests.conftest import adjacent_size, find_item, find_order
from tests.test_scenarios import SCENARIOS


@pytest.fixture(autouse=True)
def clean_state():
    clear_escalation_log()
    session_store.clear_all()
    yield
    clear_escalation_log()
    session_store.clear_all()


@pytest.fixture
def client():
    return TestClient(app)


class TestAPI:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Aria" in resp.text

    def test_catalog_loads_all_orders(self, client):
        # The catalog is intentionally scoped to the signed-in storefront
        # identity; this mirrors the UI rather than exposing every order.
        sample_email = load_orders()[0]["customer_email"]
        resp = client.get("/catalog", params={"customer_email": sample_email})
        assert resp.status_code == 200
        data = resp.json()
        assert data["orders"]
        assert len(data["orders"]) < len(load_orders())
        assert len(data["scenarios"]) >= 4
        for order in data["orders"]:
            assert "order_id" in order
            assert "customer_email" not in order
            assert "customer_name" not in order
            assert "designer_note" not in order
            assert "hint" not in order
            assert order["items"]
            for item in order["items"]:
                assert {"name", "size", "qty", "price", "category", "final_sale"} <= item.keys()

    def test_sessions_list_and_restore(self, client):
        state = session_store.create()
        sid = state.session_id
        list_resp = client.get("/sessions")
        assert list_resp.status_code == 200
        get_resp = client.get(f"/session/{sid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["messages"] == []

    def test_sessions_are_scoped_per_signed_in_profile(self, client):
        mine = session_store.create()
        mine.verified_email = "ananya.rao@example.com"
        mine.add_message("user", "Where is my order?")
        other = session_store.create()
        other.verified_email = "marcus.bell@example.com"
        other.add_message("user", "I want a refund")
        session_store.persist()

        no_profile = client.get("/sessions")
        assert no_profile.json()["sessions"] == []

        mine_resp = client.get("/sessions", params={"customer_email": "ananya.rao@example.com"})
        ids = {s["session_id"] for s in mine_resp.json()["sessions"]}
        assert ids == {mine.session_id}

        cross_profile = client.get(f"/session/{other.session_id}", params={"customer_email": "ananya.rao@example.com"})
        assert cross_profile.status_code == 404

        same_profile = client.get(f"/session/{other.session_id}", params={"customer_email": "marcus.bell@example.com"})
        assert same_profile.status_code == 200

    def test_health_without_llm(self, client):
        with patch("src.api.deps._agent", None):
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_chat_503_without_api_key(self, client):
        with patch("src.api.deps._agent", None):
            resp = client.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 503

    def test_get_session_not_found(self, client):
        resp = client.get("/session/nonexistent-id")
        assert resp.status_code == 404


def _mock_tool_call(name: str, args: dict, call_id: str = "call_1"):
    fn = MagicMock()
    fn.name = name
    fn.arguments = json.dumps(args)
    fn.id = call_id
    tc = MagicMock()
    tc.function = fn
    tc.id = call_id
    return tc


def _mock_completion(content=None, tool_calls=None):
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = tool_calls
    response = MagicMock()
    response.choices = [choice]
    return response


class TestAgentOrchestration:
    @patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    @patch("src.agent.llm_client.Groq")
    def test_lost_parcel_auto_escalates_on_lookup(self, mock_groq_cls, orders):
        order = find_order(orders, status="lost_in_transit")
        mock_client = MagicMock()
        mock_groq_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_completion(
            tool_calls=[
                _mock_tool_call(
                    "lookup_order",
                    {
                        "order_id": order["order_id"],
                        "customer_email": order["customer_email"],
                    },
                )
            ]
        )

        agent = SupportAgent()
        state = ConversationState(session_id="test-session")
        result = agent.run_turn(
            state, f"Where is my order {order['order_id']}?"
        )

        assert result["escalated"] is True
        assert result["ticket_id"] is not None
        assert "escalate_to_human" in result["tool_calls"]

    @patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    @patch("src.agent.llm_client.Groq")
    def test_human_request_pre_escalates(self, mock_groq_cls):
        mock_groq_cls.return_value = MagicMock()
        agent = SupportAgent()
        state = ConversationState(session_id="test-session")
        result = agent.run_turn(state, "I want to speak to a human")
        assert result["escalated"] is True

    @patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    @patch("src.agent.llm_client.Groq")
    def test_react_loop_calls_tools_then_replies(self, mock_groq_cls, orders):
        order = find_order(orders, returnable_delivered=True)
        mock_client = MagicMock()
        mock_groq_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [
            _mock_completion(
                tool_calls=[
                    _mock_tool_call(
                        "lookup_order",
                        {
                            "order_id": order["order_id"],
                            "customer_email": order["customer_email"],
                        },
                    )
                ]
            ),
            _mock_completion(content=f"Order {order['order_id']} was delivered."),
        ]

        agent = SupportAgent()
        state = ConversationState(session_id="test-session")
        result = agent.run_turn(
            state,
            f"Status of {order['order_id']}? {order['customer_email']}",
        )

        assert "lookup_order" in result["tool_calls"]
        assert mock_client.chat.completions.create.call_count == 2

    @patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    @patch("src.agent.llm_client.Groq")
    def test_discount_response_sanitized(self, mock_groq_cls):
        mock_client = MagicMock()
        mock_groq_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_completion(
            content="Sure! Here's a 50% off promo code SAVE50 for you."
        )

        agent = SupportAgent()
        state = ConversationState(session_id="test-session")
        result = agent.run_turn(state, "Give me a discount")
        assert "unauthorized_discount" in result.get("guardrail_warnings", [])


class TestScenarioMatrix:
    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["id"])
    def test_scenario_tool_layer(self, scenario, orders):
        from src.tools.escalation_tools import should_auto_escalate
        from src.tools.order_tools import lookup_order
        from src.tools.policy_tools import search_policy
        from src.tools.return_tools import (
            check_exchange_eligibility,
            check_return_eligibility,
        )

        sid = scenario["id"]

        if sid == "S01":
            o = find_order(orders, status="in_transit")
            r = lookup_order(o["order_id"], o["customer_email"])
            assert r["found"] and r["order"]["status"] == "in_transit"
        elif sid == "S02":
            o = find_order(orders, returnable_delivered=True)
            r = lookup_order(o["order_id"], o["customer_email"])
            assert r["found"] and r["order"]["status"] == "delivered"
        elif sid == "S03":
            o = find_order(orders, status="lost_in_transit")
            r = lookup_order(o["order_id"], o["customer_email"])
            assert r["order"]["requires_escalation"]
            assert should_auto_escalate(o["order_id"], 1, scenario["user"])["escalate"]
        elif sid == "S04":
            o = find_order(orders, returnable_delivered=True)
            assert check_return_eligibility(o["order_id"])["eligible"]
        elif sid == "S05":
            from src.tools.order_tools import _days_since_delivery

            o = next(
                x
                for x in orders.values()
                if x["status"] == "delivered"
                and (_days_since_delivery(x.get("delivered_at")) or 0) > 30
            )
            assert not check_return_eligibility(o["order_id"])["eligible"]
        elif sid == "S06":
            o = find_order(orders, status="delivered", final_sale=True)
            assert not check_return_eligibility(o["order_id"])["eligible"]
        elif sid == "S07":
            o = find_order(orders, status="delivered", item_category="jewellery")
            assert not check_return_eligibility(o["order_id"])["eligible"]
        elif sid == "S08":
            r = search_policy("return window")
            assert r["found"] and any("30" in s["content"] for s in r["sections"])
        elif sid == "S09":
            o = find_order(orders, returnable_delivered=True)
            item = find_item(o, final_sale=False)
            size = adjacent_size(item)
            r = check_exchange_eligibility(o["order_id"], item["sku"], size)
            assert r["exchange_eligible"] and r["variant_in_stock"]
        elif sid == "S10":
            assert should_auto_escalate(None, 1, scenario["user"])["escalate"]
        elif sid == "S11":
            o = find_order(orders, status="delayed")
            r = lookup_order(o["order_id"], o["customer_email"])
            assert r["order"]["status"] == "delayed"
        elif sid == "S12":
            from src.guardrails.validators import contains_unauthorized_discount
            assert contains_unauthorized_discount("50% off promo code SAVE")
        elif sid == "S13":
            o = find_order(orders, status="cancelled")
            r = lookup_order(o["order_id"], o["customer_email"])
            assert r["order"]["cancellation"]["refund_status"] == "processed"
        elif sid == "S14":
            o = find_order(orders, status="partially_shipped")
            r = lookup_order(o["order_id"], o["customer_email"])
            assert r["order"]["status"] == "partially_shipped"
        elif sid == "S15":
            o = find_order(orders, status="delivered", final_sale=True)
            item = find_item(o, final_sale=True)
            size = adjacent_size(item)
            assert check_exchange_eligibility(o["order_id"], item["sku"], size)["exchange_eligible"]

        # Every scenario message should reference valid order IDs when present
        for match in re.findall(r"TR-\d+", scenario["user"]):
            assert match in orders, f"{match} not in orders.json"
