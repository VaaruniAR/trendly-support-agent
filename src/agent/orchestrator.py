"""
ReAct agent orchestrator — Groq function-calling loop.

Flow per turn:
  1. Pre-check auto-escalation rules
  2. Call Groq with tool definitions
  3. Execute tool(s), append results, repeat until text reply or max iterations
  4. Sanitize response (block unauthorized discounts)
"""

import json
from typing import Any

from src.agent.llm_client import GroqChatClient
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.session_effects import (
    apply_tool_args,
    apply_tool_result,
    build_context_message,
    check_lost_parcel_escalation,
)
from src.agent.state import ConversationState
from src.agent.tool_registry import TOOL_DEFINITIONS, execute_tool
from src.config import LLM_MODEL, MAX_AGENT_ITERATIONS
from src.guardrails.validators import sanitize_response
from src.services.return_intake import handle_return_intake
from src.services.cancellation import cancellation_response
from src.tools.escalation_tools import escalate_to_human, should_auto_escalate
from src.tools.policy_tools import full_return_policy


class SupportAgent:
    """ReAct loop: LLM decides which tools to call until it produces a final text reply."""

    def __init__(self) -> None:
        self._llm = GroqChatClient()

    def run_turn(self, state: ConversationState, user_message: str) -> dict[str, Any]:
        auto = should_auto_escalate(state.active_order_id, state.contact_count, user_message)
        if auto and not state.escalated:
            return self._auto_escalate(state, user_message, auto)

        if self._is_full_return_policy_request(user_message):
            reply = full_return_policy()["policy"]
            state.add_message("user", user_message)
            state.add_message("assistant", reply)
            return {
                "reply": reply,
                "escalated": state.escalated,
                "ticket_id": state.escalation_ticket,
                "tool_calls": ["search_policy"],
            }

        if self._is_cancellation_request(user_message):
            order_id = self._order_id_from_message(user_message) or state.active_order_id
            result = cancellation_response(order_id, user_message)
            if result is not None:
                state.add_message("user", user_message)
                state.add_message("assistant", result["reply"])
                return {
                    "reply": result["reply"],
                    "escalated": state.escalated,
                    "ticket_id": state.escalation_ticket,
                    "tool_calls": [],
                }

        # The return journey is a deterministic workflow.  This happens before
        # the LLM tool loop so a model can never skip collecting a reason (or
        # required §6.1 evidence) and immediately create a return.
        intake = handle_return_intake(state, user_message)
        if intake is not None:
            state.add_message("user", user_message)
            state.add_message("assistant", intake["reply"])
            return {
                "reply": intake["reply"],
                "escalated": state.escalated,
                "ticket_id": state.escalation_ticket,
                "tool_calls": intake.get("tool_calls", []),
                "awaiting_evidence": intake.get("awaiting_evidence", False),
                "choices": intake.get("choices", []),
            }

        state.add_message("user", user_message)
        messages = self._build_messages(state)
        tool_calls_log: list[str] = []

        for _ in range(MAX_AGENT_ITERATIONS):
            response = self._llm.create(
                model=LLM_MODEL,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.2,
            )

            assistant_msg = response.choices[0].message
            if assistant_msg.tool_calls:
                messages.append(self._assistant_tool_message(assistant_msg))

                for tc in assistant_msg.tool_calls:
                    name = tc.function.name
                    args = json.loads(tc.function.arguments or "{}")
                    tool_calls_log.append(name)

                    apply_tool_args(state, name, args)
                    result = execute_tool(name, args)
                    apply_tool_result(state, name, result)

                    if name == "lookup_order":
                        early = check_lost_parcel_escalation(state, result)
                        if early:
                            early["tool_calls"] = tool_calls_log + ["escalate_to_human"]
                            return early

                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                continue

            reply = assistant_msg.content or "I'm sorry, I couldn't generate a response."
            reply, warnings = sanitize_response(reply)
            state.add_message("assistant", reply)
            return {
                "reply": reply,
                "escalated": state.escalated,
                "ticket_id": state.escalation_ticket,
                "tool_calls": tool_calls_log,
                "guardrail_warnings": warnings,
            }

        return self._iteration_limit_fallback(state, user_message, tool_calls_log)

    def _auto_escalate(
        self, state: ConversationState, user_message: str, auto: dict[str, Any]
    ) -> dict[str, Any]:
        esc = escalate_to_human(
            reason=auto["reason"],
            summary=f"Auto-escalation triggered. Last message: {user_message}",
            customer_email=state.verified_email,
            order_id=state.active_order_id,
            priority=auto.get("priority", "normal"),
        )
        state.escalated = True
        state.escalation_ticket = esc["ticket_id"]
        state.add_message("user", user_message)
        reply = esc["message"] + "\n\nA specialist will review your case shortly."
        state.add_message("assistant", reply)
        return {
            "reply": reply,
            "escalated": True,
            "ticket_id": esc["ticket_id"],
            "tool_calls": ["escalate_to_human"],
        }

    def _build_messages(self, state: ConversationState) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if ctx := build_context_message(state):
            messages.append({"role": "system", "content": ctx})
        messages.extend(state.messages)
        return messages

    @staticmethod
    def _assistant_tool_message(assistant_msg: Any) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": assistant_msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in assistant_msg.tool_calls
            ],
        }

    @staticmethod
    def _is_full_return_policy_request(message: str) -> bool:
        text = message.lower()
        return "return policy" in text or (
            "return" in text and any(word in text for word in ("entire", "full", "all", "complete"))
        )

    @staticmethod
    def _is_cancellation_request(message: str) -> bool:
        return any(word in message.lower() for word in ("cancel", "cancellation"))

    @staticmethod
    def _order_id_from_message(message: str) -> str | None:
        import re
        match = re.search(r"\bTR[-\s]?(\d{4})\b", message, re.I)
        return f"TR-{match.group(1)}" if match else None

    def _iteration_limit_fallback(
        self, state: ConversationState, user_message: str, tool_calls_log: list[str]
    ) -> dict[str, Any]:
        fallback = escalate_to_human(
            reason="Agent iteration limit reached",
            summary=f"Could not resolve within {MAX_AGENT_ITERATIONS} steps. Last user message: {user_message}",
            customer_email=state.verified_email,
            order_id=state.active_order_id,
        )
        state.escalated = True
        state.escalation_ticket = fallback["ticket_id"]
        reply = fallback["message"]
        state.add_message("assistant", reply)
        return {
            "reply": reply,
            "escalated": True,
            "ticket_id": fallback["ticket_id"],
            "tool_calls": tool_calls_log + ["escalate_to_human"],
        }
