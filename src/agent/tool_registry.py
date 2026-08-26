"""Agent tool schemas and dispatch — single registry for Groq function-calling."""

import json
from typing import Any, Callable

from src.tools.escalation_tools import escalate_to_human
from src.tools.order_tools import list_customer_orders, lookup_order
from src.tools.policy_tools import search_policy
from src.tools.return_tools import (
    check_exchange_eligibility,
    check_return_eligibility,
    initiate_exchange,
    initiate_return,
)

ToolFn = Callable[..., dict[str, Any]]

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up order details by order ID. order_id alone is enough for status/tracking updates. Pass customer_email as well when the request is a return or exchange, to verify account ownership before initiating it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID from the customer's order confirmation"},
                    "customer_email": {
                        "type": "string",
                        "description": "Optional — only required before initiating a return or exchange, to verify account ownership.",
                    },
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_customer_orders",
            "description": "List all orders for a customer email address.",
            "parameters": {
                "type": "object",
                "properties": {"customer_email": {"type": "string"}},
                "required": ["customer_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": "Search the official Trendly shipping & returns policy. REQUIRED before answering any policy question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Policy topic to search e.g. 'return window', 'express shipping'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_return_eligibility",
            "description": "Check if order/items are eligible for return per policy rules. Call before initiating return.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific item IDs to check; omit to check all items",
                    },
                    "reason": {
                        "type": "string",
                        "enum": ["change_of_mind", "damaged", "wrong_item", "defective", "exchange"],
                        "description": "Return reason",
                    },
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_exchange_eligibility",
            "description": "Check SIZE exchange eligibility and stock. Size only — not colour/style (§4.1).",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "item_id": {"type": "string"},
                    "desired_size": {"type": "string"},
                    "desired_color": {"type": "string"},
                },
                "required": ["order_id", "item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_return",
            "description": "Start a return after eligibility confirmed and email verified.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "customer_email": {"type": "string"},
                },
                "required": ["order_id", "item_ids", "reason", "customer_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_exchange",
            "description": "Start a SIZE exchange after eligibility and stock confirmed. Size only (§4.1).",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "item_id": {"type": "string"},
                    "desired_size": {"type": "string"},
                    "customer_email": {"type": "string"},
                },
                "required": ["order_id", "item_id", "desired_size", "customer_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Hand off to a human agent with structured summary. REQUIRED for lost-in-transit (§1.6), "
                "COD refunds (§3.3), or when unable to resolve."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why escalating"},
                    "summary": {
                        "type": "string",
                        "description": "Concise handoff summary: issue, actions taken, recommended next step",
                    },
                    "customer_email": {"type": "string"},
                    "order_id": {"type": "string"},
                    "priority": {"type": "string", "enum": ["normal", "high"], "description": "Ticket priority"},
                },
                "required": ["reason", "summary"],
            },
        },
    },
]

TOOL_DISPATCH: dict[str, ToolFn] = {
    "lookup_order": lookup_order,
    "list_customer_orders": list_customer_orders,
    "search_policy": search_policy,
    "check_return_eligibility": check_return_eligibility,
    "check_exchange_eligibility": check_exchange_eligibility,
    "initiate_return": initiate_return,
    "initiate_exchange": initiate_exchange,
    "escalate_to_human": escalate_to_human,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Run one tool and return JSON string for the Groq tool result message."""
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return json.dumps(fn(**arguments), default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "tool": name})
