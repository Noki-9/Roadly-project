from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parent

from core.env_config import load_dotenv

load_dotenv()

from core.pydantic_models import Roadmap, RoadmapRequest
from llm.demo import demo_roadmap

LLM_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or os.getenv("OPENROUTER_API_KEY")
    or ""
).strip()
LLM_BASE_URL = (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
LLM_CHAT_URL = (os.getenv("LLM_CHAT_URL") or f"{LLM_BASE_URL}/chat/completions").strip()
LLM_MODEL = os.getenv("LLM_MODEL") or "gpt-4o-mini"
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))
LLM_ALLOW_NO_KEY = os.getenv("LLM_ALLOW_NO_KEY", "").lower() in {"1", "true", "yes", "on"}
DEMO_MODE = os.getenv("ROADLY_DEMO", "").lower() in {"1", "true", "yes", "on"}


from core.utilit import check_rate_limit, client_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT, connect=15.0))
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(title="Roadly", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/scripts", StaticFiles(directory=BASE_DIR / "scripts"), name="scripts")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret-change-me"))
templates = Jinja2Templates(directory=BASE_DIR / "templates")


from llm.llm_calls import call_llm


# ---------------------------------------------------------------------------
# Маршруты
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, error: str | None = None, login: str | None = None):
    return templates.TemplateResponse(
        request, "index.html", {"error": error, "login": login}
    )


@app.post("/api/roadmap", response_model=Roadmap)
async def create_roadmap(data: RoadmapRequest, request: Request) -> Roadmap:
    check_rate_limit(client_key(request))

    if DEMO_MODE or not (LLM_API_KEY or LLM_ALLOW_NO_KEY):
        # Небольшая задержка, чтобы интерфейс прожил состояние загрузки.
        await asyncio.sleep(0.7)
        return demo_roadmap(data)

    assert request.app.state.http is not None
    return await call_llm(data)
