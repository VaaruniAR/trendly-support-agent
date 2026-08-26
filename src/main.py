"""FastAPI entry — static chat UI + REST API for the support agent."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import src.env_loader  # noqa: F401 — loads .env before anything else

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.agent.orchestrator import SupportAgent
from src.api import deps
from src.api.router import router
from src.config import ASSISTANT_NAME, STORE_NAME
from src.env_loader import is_groq_key_configured

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if is_groq_key_configured():
        deps.set_agent(SupportAgent())
        print(f"Aria agent ready (GROQ_SSL_VERIFY={os.getenv('GROQ_SSL_VERIFY', 'true')})")
    else:
        print("Warning: Set GROQ_API_KEY in .env (https://console.groq.com)")
    yield


app = FastAPI(title=f"{ASSISTANT_NAME} — {STORE_NAME} Support", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def no_stale_cache(request: Request, call_next):
    """Force browsers to revalidate the HTML shell and JS/CSS on every visit.

    Without this, mobile Safari/Chrome can silently keep serving an old cached
    bundle after a redeploy (no cache-busting on /static/* URLs), which looks
    like a broken app on phones that visited before a fix shipped.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    index = STATIC_DIR / "index.html"
    return FileResponse(index) if index.is_file() else {"service": f"{ASSISTANT_NAME} Support"}
