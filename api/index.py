"""Vercel serverless entrypoint — re-exports the FastAPI ASGI app.

Vercel's Python runtime auto-detects an ASGI-callable named `app` in a file
under /api and serves it as a function. All other deploy targets (Render,
local `./run.sh`) run `src.main:app` directly and never import this file.
"""

from src.main import app  # noqa: F401
