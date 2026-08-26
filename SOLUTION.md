# Solution Note — Aria, Trendly Support Agent

**Author:** Vaaruni Ramesh · **Assignment:** Build an Agentic Support Assistant (Yellow.ai FDE Intern screening)

## 1. Architecture

```
Browser (vanilla JS chat UI)
        │  REST (JSON)
        ▼
FastAPI (src/main.py, src/api/router.py)
        │
        ▼
SupportAgent — ReAct orchestrator (src/agent/orchestrator.py)
        │
        ├─ Deterministic pre-checks (run before the LLM sees the turn)
        │    ├─ should_auto_escalate() — human phrases, legal/media threats,
        │    │    3+ contacts, lost-in-transit, high-value order, bank-detail attempts
        │    ├─ handle_return_intake() — a hand-written state machine that collects
        │    │    item → reason → (photo, if damaged/defective/wrong-item) → confirm,
        │    │    and only then calls the return tools. The model narrates each step
        │    │    but cannot skip one.
        │    └─ cancellation_response() — answers cancellation questions strictly
        │         from what the policy actually says (nothing, for in-flight orders),
        │         instead of letting the model guess.
        │
        └─ Groq function-calling loop (openai/gpt-oss-120b), bounded to 8 iterations
             tools: lookup_order, list_customer_orders, search_policy,
                    check_return_eligibility, check_exchange_eligibility,
                    initiate_return, initiate_exchange, escalate_to_human
             │
             ├─ order service      → data/orders.json (10 fixed orders, read-only)
             ├─ policy service     → keyword-scored section retrieval over
             │                        data/trendly_policy.md (no vector DB — the
             │                        doc is 7 short sections, so full-text +
             │                        topic-boost keywords retrieve accurately
             │                        without embedding infrastructure)
             ├─ return/exchange    → eligibility rules mirrored from the policy
             │                        (final sale, non-returnable categories,
             │                        48-hour damage window, footwear box
             │                        deduction, etc.), independent of the LLM
             ├─ evidence store     → damage/defect/wrong-item photos are saved to
             │                        a local, git-ignored store and linked to a
             │                        human-review ticket — the app never judges
             │                        photo authenticity itself
             └─ escalation service → structured ticket with reason, priority,
                                      and a human-usable summary
        │
        ▼
Guardrail sanitizer (src/guardrails/validators.py) — regex last line of
defense against hallucinated discount codes or over-promised refund speed,
applied to every model-authored reply before it reaches the customer.
```

Chat history and evidence records persist to local JSON (`data/chat_sessions.json`,
`data/evidence_records.json`), scoped per signed-in profile.

## 2. Key trade-offs

- **A hand-written state machine owns the return flow, not the LLM.** The
  model is excellent at conversation but a return that skips the reason or the
  required §6.1 photo is a real, costly failure mode — not a stylistic one. Taking
  that path out of the model's hands costs some conversational flexibility (the
  intake order is fixed) but removes an entire class of "the agent forgot a
  step" bugs, and end-to-end tests can verify it deterministically instead of
  by re-prompting.
- **Keyword-scored retrieval over embeddings for policy search.** With a
  7-section, single-file policy document, a small topic-boost keyword map
  retrieves the right section reliably and is trivially auditable — you can
  read exactly why a section matched. It would not scale to a large,
  frequently-changing policy corpus; that's a real limitation, not a hidden one.
- **All photo evidence goes to a human, always.** An LLM has no reliable way
  to judge whether a photo shows real damage, and a wrong automated call in
  either direction (falsely accusing a customer, or approving a fake claim) is
  worse than adding a human step. This trades speed for trust.
- **Regex guardrails as a safety net, not the primary control.** The system
  prompt is the primary control on discount/refund language; the sanitizer
  exists because a model can still say the wrong thing even when instructed
  not to, and a deterministic check after generation is cheap insurance.
- **Local JSON files, not a database.** Correct for a single-instance
  assignment deployment; would not survive multi-instance scaling and is
  explicitly called out below as a limitation rather than assumed away.

## 3. Known limitations

- The profile switcher is a stand-in for real authentication — it proves the
  authorization boundary (one customer cannot see another's orders/chats) but
  is not production auth.
- Returns, exchanges, and escalations are recorded locally, not written to a
  real OMS, warehouse, or ticketing system.
- `orders.json` is treated as immutable per the assignment brief, so there is
  no persisted "this item was already returned" flag — re-running the same
  return in a new conversation on the same item would succeed again rather
  than being rejected. In production this would be backed by real order
  state.
- Session and evidence storage is a single local JSON file; correct for one
  instance, not for horizontal scaling, and not durable across a Render free
  tier redeploy.
- Policy retrieval is keyword-scored, not semantic. An unusually phrased
  question could, in principle, score below the retrieval threshold; the
  topic-boost map mitigates the most likely phrasings but isn't exhaustive.
- The Groq tool-calling loop is capped at 8 iterations; a genuinely
  unresolvable request escalates to a human rather than looping or guessing.

## 4. Five discovery questions for Trendly's ops team

1. What's the real system of record for orders and returns — is there an API
   this agent could call directly, or would it need to integrate with a
   legacy OMS/warehouse system through batch exports or a middleware layer?
2. Who reviews damage/defect evidence photos today, what's their SLA, and
   should that queue land inside this same chat surface or feed into an
   existing tool (Zendesk, Freshdesk, an internal ops console)?
3. What's an acceptable false-escalation rate versus false-auto-resolve
   rate — is it worse for the agent to hand a human a case it could have
   closed itself, or to let it resolve something it shouldn't have?
4. How should customer identity actually be verified in production — a
   storefront auth session/JWT, OTP, magic link — and what data-residency or
   PII constraints apply to what the agent is allowed to display?
5. How often does the shipping/returns policy change, and should grounding
   come from a live, versioned CMS document instead of a static file bundled
   with the app — and do different categories, regions, or storefronts need
   different policy variants?
