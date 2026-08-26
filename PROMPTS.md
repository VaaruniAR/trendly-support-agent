# Prompt Engineering Notes — Aria

This is an honest record of the prompts and constraints used to shape Aria. It documents the current implementation rather than inventing a development history.

## System prompt goals

Aria is a concise, professional Trendly customer-support assistant. Its responsibilities are order support, shipping and policy questions, returns, exchanges, refunds, and human escalation.

The core grounding rules are:

1. Tool results are authoritative for order facts.
2. `search_policy` is required before answering a policy question.
3. `lookup_order` is required before stating order status, dates, items, tracking, or refund facts.
4. Deterministic eligibility results cannot be overridden by conversational language.
5. A completed action may be confirmed only after the action tool reports success.
6. When the customer has an active signed-in identity, do not ask for email verification again.
7. A return begins with a selected item and return reason. Damage, defect, and wrong-item claims request the photographs required by §6.1 and route evidence to a specialist; the assistant must not call a photo fake or accuse the customer of fraud.

## Tool-use instructions

The prompt directs the model to choose structured tools rather than simulate data:

| Need | Tool sequence |
| --- | --- |
| Order status/details | `lookup_order` |
| Policy question | `search_policy` |
| Return | `check_return_eligibility` before `initiate_return` |
| Exchange | `check_exchange_eligibility` before `initiate_exchange` |
| Refund status | `get_refund_status` |
| Human request, ambiguity, failure, sensitive issue | `escalate_to_human` |

Tool inputs are validated and return JSON-shaped deterministic results. The agent is limited to a bounded ReAct loop; a non-resolving loop escalates rather than fabricating an answer.

## Safety rules

The prompt and application guardrails prohibit:

- Invented Trendly policy or ecommerce assumptions.
- Unauthorized discounts or promotional credit.
- Disclosure of system prompts, secrets, hidden instructions, or chain-of-thought.
- Cross-customer order access and arbitrary customer-data lists.
- Processing a lost parcel as a normal return.
- Collecting bank details in chat.

The application also pre-checks high-risk situations, validates customer identity at the tool boundary, and sanitizes unsafe model output.

## Few-shot behavior targets

The actual prompt uses concise examples to reinforce these patterns:

- Ask for an order ID when no signed-in order context exists.
- Use the active order for a follow-up such as “Can I return it?”
- Explain an ineligible Final Sale return without offering a nonexistent workaround.
- Confirm a supported size exchange only after eligibility is returned.
- Create a useful escalation summary when a customer asks for a person.
- Respond to injection attempts with a brief refusal and redirect to support.

## Iterations that mattered

- **Tool-first grounding:** strengthened from guidance to a requirement after testing showed that conversational models can answer generic policy questions without retrieval.
- **Signed-in state:** the orchestrator binds protected tool arguments to the active customer identity, preventing an LLM argument or user text from substituting another email.
- **Failure truthfulness:** action and tool failure paths explicitly avoid success language and can escalate.
- **Focused model context:** policy is retrieved through a small transparent service rather than a vector database because the supplied policy is short.

## Known limitations

- The demo customer selector is not production authentication.
- Actions are local simulated operations; a commerce backend would be needed for live returns/exchanges.
- The default file-backed session store is appropriate for the assignment, not multi-instance deployment.
- Image evidence is validated, then persisted to a local, git-ignored evidence store (`src/services/evidence_store.py`) and linked to the resulting escalation ticket. The workflow hands every claim to a human reviewer rather than making an automated authenticity judgement.
- Product illustrations are UI visuals; order names, sizes, prices, statuses, and dates always come from the supplied data.
