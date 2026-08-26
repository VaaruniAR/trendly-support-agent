"""Policy search — keyword-scored retrieval from trendly_policy.md (no embeddings)."""
import re
from dataclasses import dataclass

from src.data_loader import load_policy


@dataclass
class PolicySection:
    title: str
    content: str
    section_id: str


def _parse_sections(text: str) -> list[PolicySection]:
    sections: list[PolicySection] = []
    current_title = "Overview"
    current_lines: list[str] = []
    current_id = "0"

    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append(
                    PolicySection(
                        title=current_title,
                        content="\n".join(current_lines).strip(),
                        section_id=current_id,
                    )
                )
            current_title = line[3:].strip()
            match = re.match(r"^(\d+)\.", current_title)
            current_id = match.group(1) if match else current_title[:20]
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append(
            PolicySection(
                title=current_title,
                content="\n".join(current_lines).strip(),
                section_id=current_id,
            )
        )
    return sections


def search_policy(query: str, max_sections: int = 3) -> dict:
    """Search the official Trendly policy document for relevant sections."""
    query_lower = query.lower()
    keywords = [w for w in re.findall(r"[a-z0-9]+", query_lower) if len(w) > 2]

    topic_boosts = {
        "return": ["2.", "return", "window"],
        "exchange": ["4.", "exchange", "size"],
        "refund": ["3.", "refund", "timeline"],
        "ship": ["1.", "shipping", "delivery", "dispatch"],
        "deliver": ["1.", "delivery", "estimate"],
        "delay": ["1.5", "delayed", "store credit"],
        "lost": ["1.6", "lost", "parcel"],
        "partial": ["1.4", "backorder", "partial"],
        "cancel": ["2.6", "cancelled"],
        "final sale": ["2.4", "final sale"],
        "innerwear": ["2.3", "innerwear", "socks"],
        "jewel": ["2.3", "jewellery"],
        "footwear": ["2.5", "shoe box"],
        "pickup": ["5.", "pickup", "reverse"],
        "damage": ["6.", "damaged", "wrong item"],
        "cod": ["3.3", "cash on delivery", "bank"],
        "escalat": ["7.", "human", "must not"],
        "discount": ["7.", "coupon", "goodwill"],
    }

    sections = _parse_sections(load_policy())
    scored: list[tuple[float, PolicySection]] = []

    for section in sections:
        blob = (section.title + " " + section.content).lower()
        score = 0.0
        for kw in keywords:
            if kw in blob:
                score += 2.0
        for trigger, hints in topic_boosts.items():
            if trigger in query_lower:
                if any(h in blob or h in section.section_id for h in hints):
                    score += 3.0
        if score > 0:
            scored.append((score, section))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [s for _, s in scored[:max_sections]]

    if not top:
        return {
            "found": False,
            "message": (
                "No matching policy section found. Do not invent policy — "
                "escalate or say you cannot find it."
            ),
            "sections": [],
        }

    return {
        "found": True,
        "sections": [
            {"section": s.title, "content": s.content, "section_id": s.section_id}
            for s in top
        ],
        "instruction": "Answer ONLY using the sections above. If the answer is not covered, say so explicitly.",
    }


def full_return_policy() -> dict:
    """Complete customer-readable rendering of the return-related official policy."""
    return {
        "found": True,
        "policy": (
            "**Return window**\n"
            "- Items can be returned within 30 calendar days of delivery. Requests after 30 days are not eligible.\n"
            "- Items must be unworn, unwashed, with original tags attached and original packaging where provided.\n\n"
            "**Items that cannot normally be returned or exchanged**\n"
            "- Innerwear and socks, jewellery, beauty and fragrance products, face masks, and gift cards.\n"
            "- Final Sale items can be exchanged for size only; they cannot be refunded or credited.\n"
            "- Footwear must be returned in its original shoe box. Without the box, ₹300 is deducted.\n"
            "- Cancelled orders cannot have a return raised.\n\n"
            "**Refunds**\n"
            "- Refunds are issued after the returned item reaches the warehouse and passes inspection, which takes 2–3 business days.\n"
            "- Card refunds take 5–7 business days after inspection; UPI takes 3–5; cash on delivery takes 7–10 through a secure human-agent process; store-credit refunds are immediate.\n"
            "- The ₹99 original shipping fee is refunded only for a wrong, damaged, or defective item. It is not refunded for change-of-mind returns.\n"
            "- Partial returns are refunded only for the returned items.\n\n"
            "**Pickup and special cases**\n"
            "- Reverse pickup is free on serviceable pincodes and can be attempted up to two times. Non-serviceable locations can self-ship and claim up to ₹150 with a courier receipt.\n"
            "- Damaged, defective, or incorrect items must be reported within 48 hours of delivery with photographs. Trendly offers either a free replacement or a full refund including shipping, at the customer’s choice.\n"
            "- For cash-on-delivery refunds, bank details are collected by a human agent through a secure link, never in chat."
        ),
        "source": "trendly_policy.md",
    }
