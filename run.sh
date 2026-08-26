#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

pip install -q -r requirements.txt

if [ "${1:-}" = "test" ]; then
  TEST_STORE="$(mktemp -d)/chat_sessions.json"
  TRENDLY_SESSIONS_PATH="$TEST_STORE" python -m pytest "${@:2}"
  exit 0
fi

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if [ -z "${GROQ_API_KEY:-}" ]; then
  echo "Warning: GROQ_API_KEY not set. Copy .env.example to .env and add your free Groq key."
  echo "Get one at: https://console.groq.com"
fi

echo "Starting Aria on http://localhost:8000"
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
