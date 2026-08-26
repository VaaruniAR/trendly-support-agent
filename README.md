# Aria — Trendly Customer Support

Aria is a customer-support web app for Trendly. It helps a signed-in customer check their own orders, understand Trendly policy, start supported return or exchange flows, and request a human handoff.

## Live demo

**[https://trendly-aavy.onrender.com](https://trendly-aavy.onrender.com)**

- Free-tier Render instance — if it's been idle, the first request can take up to ~50s to wake up before the page responds.
- The app's simulated "today" for return-window math is fixed at **26 July 2026** (`src/config.py`), matching the assignment's order data — dates in Aria's replies are relative to that, not the actual calendar date.
- Choose a profile (top right) to see that customer's orders and chat history — each of the four sample customers only ever sees their own data.

## What it does

- Uses a Groq function-calling agent to select structured support tools.
- Grounds order facts exclusively in `data/orders.json`.
- Grounds policy answers exclusively in `data/trendly_policy.md`.
- Applies deterministic eligibility and authorization logic outside the model.
- Persists chat state locally and keeps a current signed-in customer context.
- Shows customer-scoped order cards, detailed order previews, and human handoff state.
- Guides return intake through item selection and reason collection; damage, defect, and wrong-item claims collect policy-required photo evidence for human review.
- Refuses unsupported discounts, policy invention, data leakage, and instruction-injection attempts.

## Architecture

```text
Browser UI → FastAPI API → ReAct orchestrator → structured tools
                                              ├─ order service
                                              ├─ policy service
                                              ├─ return/exchange service
                                              └─ escalation service
```

The model handles conversation and tool selection. Python code owns order lookup, policy retrieval, authorization, eligibility, actions, and escalation records. The return/exchange journey itself is a deterministic state machine (`src/services/return_intake.py`) that runs before the model's tool loop, so it cannot be skipped or reordered by the conversation. See [SOLUTION.md](SOLUTION.md) for the full architecture writeup, trade-offs, and known limitations.

## Run locally

Requirements: Python 3.11+ and a free Groq API key.

```bash
cp .env.example .env
# Add GROQ_API_KEY=gsk_... to .env
./run.sh
```

Open [http://localhost:8000](http://localhost:8000). The same script creates `.venv`, installs dependencies, loads `.env`, and starts FastAPI.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | Yes for live chat | Free Groq API key. Never commit it. |
| `GROQ_SSL_VERIFY` | No | Set `false` only for a known local/corporate TLS issue. |
| `TRENDLY_SESSIONS_PATH` | No | Alternate chat-session file, used by tests. |

Without a Groq key, the UI and health endpoint start but live chat remains unavailable.

## Tests and data verification

```bash
./run.sh test -q
```

The suite covers deterministic tools, agent/tool orchestration, safety guardrails, session behavior, return intake, cancellation handling, evidence storage, and API flows. `tests/test_data_integrity.py` verifies all 10 orders and every UI-visible order fact against the immutable `data/orders.json` source.

## Deploy on Render

`render.yaml` is ready for a Render Web Service (this is how the live demo above is deployed).

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint** and select the repository (or create a Web Service manually).
3. Set the secret `GROQ_API_KEY` directly in the service's **Environment** tab (the blueprint intentionally leaves it out of `render.yaml` via `sync: false` — never commit a real key).
4. Deploy. Render uses `pip install -r requirements.txt` and starts `uvicorn src.main:app --host 0.0.0.0 --port $PORT`.
5. Confirm `<your-render-url>/health` returns `status: "ok"` and `llm_configured: "True"`.

The app does not require a database. On a free instance, local chat sessions are ephemeral across restarts; production persistence can be added later without changing the tool layer.

## Security and product notes

- `orders.json` is assignment data and is never modified by the app.
- The browser catalog is scoped to the selected storefront customer; it never returns a cross-customer order directory.
- `.env` and persisted local conversations are ignored by Git.
- Do not set `GROQ_SSL_VERIFY=false` in a public deployment.
- The customer switcher is a demo authorization boundary for the supplied dataset, not a replacement for real production authentication.
- Return photos for damage/defect/wrong-item claims are validated, then saved to a local, git-ignored evidence store (`data/return_evidence/` + `data/evidence_records.json`) and linked to a human-review ticket. The application does not claim to determine image authenticity; a specialist reviews every evidence-based claim.

## AI-assisted development

This project was developed with AI coding assistance (Claude). The implementation, policy/data grounding, and automated test outcomes in this repository were inspected and verified locally rather than accepted blindly. See [PROMPTS.md](PROMPTS.md) for the actual system prompt, the prompting approach, and known limitations, and [SOLUTION.md](SOLUTION.md) for the architecture note and discovery questions.
