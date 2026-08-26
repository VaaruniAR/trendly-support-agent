"""
Post-response guardrails — last line of defense after the LLM replies.

The agent prompt forbids discounts, but models can still hallucinate promo codes.
These regex checks catch that and flag/replace risky language before sending to the user.
"""
import re

# Patterns that indicate the bot offered something outside policy
DISCOUNT_PATTERNS = [
    r"\b\d+\s*%\s*off\b",
    r"\bpromo\s*code\b",
    r"\bdiscount\s*code\b",
    r"\buse\s+code\b",
    r"\bfree\s+shipping\s+code\b",
    r"\b₹\s*\d+\s*off\b",
]

# Policy-permitted store credit (§1.5 delayed orders)
POLICY_ALLOWED_CREDIT = r"₹250\s*store\s*credit"

# Over-promising refund speed the policy does not guarantee
FORBIDDEN_PROMISES = [
    r"refund within\s*[1-2]\s*business\s*days",
    r"guaranteed\s*same\s*day",
]


def contains_unauthorized_discount(text: str) -> bool:
    """Detect discount/promo language except the allowed ₹250 delayed-order credit."""
    lowered = text.lower()
    # §1.5 store credit is explicitly allowed — don't flag it
    if re.search(POLICY_ALLOWED_CREDIT, text, re.IGNORECASE):
        return False
    if "goodwill" in lowered and "credit" in lowered:
        return True
    if "store credit" in lowered and "250" not in lowered and "delayed" not in lowered:
        return True
    return any(re.search(p, lowered) for p in DISCOUNT_PATTERNS)


def contains_forbidden_promise(text: str) -> bool:
    """Detect refund timelines shorter than policy allows."""
    lowered = text.lower()
    return any(re.search(p, lowered) for p in FORBIDDEN_PROMISES)


def sanitize_response(text: str) -> tuple[str, list[str]]:
    """
    Run all guardrails on the final assistant message.
    Returns (possibly modified text, list of warning codes for logging/debug).
    """
    warnings: list[str] = []
    if contains_unauthorized_discount(text):
        warnings.append("unauthorized_discount")
        text = re.sub(
            r"(?i)(here('s| is) (a |your )?(promo|discount) code.*$)",
            "I'm not able to offer discounts or promo codes. Let me help within our standard policy instead.",
            text,
        )
    if contains_forbidden_promise(text):
        warnings.append("forbidden_promise")
    # Section markers are internal grounding metadata, not customer-facing copy.
    text = re.sub(r"\s*\(§\d+(?:\.\d+)?\)", "", text)
    return text, warnings
