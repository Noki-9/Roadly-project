from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parent

from core.env_config import load_dotenv

load_dotenv()

from core.database import get_db, init_db
from core.models import RoadmapRecord, User
from core.pydantic_models import ProgressUpdate, Roadmap, RoadmapRequest
from core.roadmap_utils import (
    build_view,
    filename_slug,
    filter_done_tasks,
    format_date_ru,
    roadmap_stats,
    roadmap_to_markdown,
)
from core.security import (
    DUMMY_PASSWORD_HASH,
    add_flash,
    csrf_valid,
    ensure_csrf,
    get_current_user,
    get_user_by_email,
    hash_password,
    login_user,
    logout_user,
    normalize_email,
    password_problem,
    pop_flashes,
    require_api_user,
    safe_next,
    validate_email,
    verify_api_csrf,
    verify_password,
)
from core.utilit import check_rate_limit, client_key
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

SESSION_SECRET = (os.getenv("SESSION_SECRET") or "").strip() or "dev-secret-change-me"
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "").lower() in {"1", "true", "yes", "on"}

AUTH_RATE_LIMIT_REQUESTS = 10
AUTH_RATE_LIMIT_WINDOW = 300.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT, connect=15.0))
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(title="Roadly", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/scripts", StaticFiles(directory=BASE_DIR / "scripts"), name="scripts")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="roadly_session",
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
    max_age=60 * 60 * 24 * 14,
)
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


def plural_ru(count: int, one: str, few: str, many: str) -> str:
    count = int(count)
    mod10 = count % 10
    mod100 = count % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and (mod100 < 10 or mod100 >= 20):
        return few
    return many


templates.env.globals["plural_ru"] = plural_ru
templates.env.globals["format_date_ru"] = format_date_ru


from llm.llm_calls import call_llm


# ---------------------------------------------------------------------------
# Вспомогательные функции страниц
# ---------------------------------------------------------------------------
def page_context(request: Request, db: Session, **extra) -> dict:
    context = {
        "current_user": get_current_user(request, db),
        "csrf_token": ensure_csrf(request),
        "flashes": pop_flashes(request),
    }
    context.update(extra)
    return context


def login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(f"/login?next={quote(target, safe='/')}", status_code=303)


def render_error(
    request: Request,
    db: Session,
    message: str,
    *,
    title: str = "Страница не найдена",
    status_code: int = 404,
):
    return templates.TemplateResponse(
        request,
        "error.html",
        page_context(
            request,
            db,
            error_title=title,
            error_message=message,
            error_code=status_code,
        ),
        status_code=status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": (
                    "Проверьте параметры запроса: цель должна содержать "
                    "минимум 10 символов, остальные поля — из списка."
                )
            },
        )
    return JSONResponse(
        status_code=422,
        content={"detail": "Некорректные данные формы. Обновите страницу и попробуйте снова."},
    )


# ---------------------------------------------------------------------------
# Страницы
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "index.html", page_context(request, db))


@app.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    next_url: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
):
    if get_current_user(request, db) is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "auth.html",
        page_context(
            request,
            db,
            mode="register",
            email="",
            next_url=safe_next(next_url, "/dashboard"),
        ),
    )


@app.post("/register", response_class=HTMLResponse)
async def register_action(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    csrf_token: str = Form(""),
    next_url: str = Form(""),
    db: Session = Depends(get_db),
):
    next_url = safe_next(next_url, "/dashboard")
    email_value = normalize_email(email)

    def fail(message: str, status_code: int = 400):
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(
                request,
                db,
                mode="register",
                email=email_value,
                next_url=next_url,
                error=message,
            ),
            status_code=status_code,
        )

    if not csrf_valid(request, csrf_token):
        return fail("Сессия устарела. Обновите страницу и попробуйте снова.")
    try:
        check_rate_limit(
            f"auth:{client_key(request)}",
            AUTH_RATE_LIMIT_REQUESTS,
            AUTH_RATE_LIMIT_WINDOW,
        )
    except HTTPException as exc:
        return fail(str(exc.detail), status_code=exc.status_code)

    email_error = validate_email(email_value)
    if email_error:
        return fail(email_error)

    password_error = password_problem(password)
    if password_error:
        return fail(password_error)

    if password != password_confirm:
        return fail("Пароли не совпадают.")

    if get_user_by_email(db, email_value) is not None:
        return fail("Аккаунт с таким email уже существует. Войдите в него.")

    user = User(email=email_value, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return fail("Аккаунт с таким email уже существует. Войдите в него.")
    db.refresh(user)

    login_user(request, user)
    add_flash(request, "Аккаунт создан. Добро пожаловать в Roadly!")
    return RedirectResponse(next_url, status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next_url: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
):
    if get_current_user(request, db) is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "auth.html",
        page_context(
            request,
            db,
            mode="login",
            email="",
            next_url=safe_next(next_url, "/dashboard"),
        ),
    )


@app.post("/login", response_class=HTMLResponse)
async def login_action(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    next_url: str = Form(""),
    db: Session = Depends(get_db),
):
    next_url = safe_next(next_url, "/dashboard")
    email_value = normalize_email(email)

    def fail(message: str, status_code: int = 400):
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(
                request,
                db,
                mode="login",
                email=email_value,
                next_url=next_url,
                error=message,
            ),
            status_code=status_code,
        )

    if not csrf_valid(request, csrf_token):
        return fail("Сессия устарела. Обновите страницу и попробуйте снова.")
    try:
        check_rate_limit(
            f"auth:{client_key(request)}",
            AUTH_RATE_LIMIT_REQUESTS,
            AUTH_RATE_LIMIT_WINDOW,
        )
    except HTTPException as exc:
        return fail(str(exc.detail), status_code=exc.status_code)

    if validate_email(email_value) is not None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return fail("Неверный email или пароль.")

    user = get_user_by_email(db, email_value)
    if user is None:
        # Выполняем bcrypt-проверку и для несуществующего email,
        # чтобы время ответа не выдавало наличие аккаунта.
        verify_password(password, DUMMY_PASSWORD_HASH)
        return fail("Неверный email или пароль.")

    if not verify_password(password, user.password_hash):
        return fail("Неверный email или пароль.")

    login_user(request, user)
    add_flash(request, "Вы вошли в аккаунт.")
    return RedirectResponse(next_url, status_code=303)


@app.post("/logout")
async def logout_action(
    request: Request,
    csrf_token: str = Form(""),
):
    if not csrf_valid(request, csrf_token):
        add_flash(
            request,
            "Не удалось выйти из аккаунта: обновите страницу и попробуйте снова.",
            "error",
        )
        return RedirectResponse("/", status_code=303)

    logout_user(request)
    add_flash(request, "Вы вышли из аккаунта.")
    return RedirectResponse("/", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return login_redirect(request)

    records = db.scalars(
        select(RoadmapRecord)
        .where(RoadmapRecord.user_id == user.id)
        .order_by(RoadmapRecord.updated_at.desc(), RoadmapRecord.id.desc())
    ).all()

    roadmap_items = []
    for record in records:
        payload = record.payload if isinstance(record.payload, dict) else {}
        roadmap_items.append(
            {
                "id": record.id,
                "title": record.title or "Ваш roadmap",
                "summary": record.summary,
                "prompt": record.prompt,
                "level": record.level,
                "pace": record.pace,
                "horizon": record.horizon,
                "demo": bool(payload.get("demo")),
                "created_at": format_date_ru(record.created_at),
                "updated_at": format_date_ru(record.updated_at),
                "stats": roadmap_stats(payload, record.done_tasks),
            }
        )

    total_tasks = sum(item["stats"]["total"] for item in roadmap_items)
    done_tasks = sum(item["stats"]["done"] for item in roadmap_items)
    overview = {
        "roadmaps": len(roadmap_items),
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "percent": round(done_tasks / total_tasks * 100) if total_tasks else 0,
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        page_context(
            request,
            db,
            roadmaps=roadmap_items,
            overview=overview,
            user_email=user.email,
        ),
    )


@app.get("/roadmaps/{roadmap_id}", response_class=HTMLResponse)
async def roadmap_page(
    roadmap_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return login_redirect(request)

    record = db.get(RoadmapRecord, roadmap_id)
    if record is None or record.user_id != user.id:
        return render_error(
            request,
            db,
            "Этот roadmap не найден или принадлежит другому аккаунту.",
        )

    payload = record.payload if isinstance(record.payload, dict) else {}
    return templates.TemplateResponse(
        request,
        "roadmap.html",
        page_context(
            request,
            db,
            record=record,
            payload=payload,
            view=build_view(payload, record.done_tasks),
            stats=roadmap_stats(payload, record.done_tasks),
            created_at=format_date_ru(record.created_at),
        ),
    )


@app.get("/roadmaps/{roadmap_id}/export.md")
async def export_roadmap(
    roadmap_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return login_redirect(request)

    record = db.get(RoadmapRecord, roadmap_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Roadmap не найден.")

    payload = record.payload if isinstance(record.payload, dict) else {}
    markdown = roadmap_to_markdown(payload, record.done_tasks)
    filename = f"{filename_slug(record.title)}.md"
    return PlainTextResponse(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/roadmaps/{roadmap_id}/delete")
async def delete_roadmap(
    roadmap_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return login_redirect(request)

    if not csrf_valid(request, csrf_token):
        add_flash(
            request,
            "Не удалось удалить roadmap: обновите страницу и попробуйте снова.",
            "error",
        )
        return RedirectResponse(f"/roadmaps/{roadmap_id}", status_code=303)

    record = db.get(RoadmapRecord, roadmap_id)
    if record is None or record.user_id != user.id:
        add_flash(request, "Roadmap не найден.", "error")
        return RedirectResponse("/dashboard", status_code=303)

    db.delete(record)
    db.commit()
    add_flash(request, "Roadmap удалён.")
    return RedirectResponse("/dashboard", status_code=303)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "demo": DEMO_MODE or not (LLM_API_KEY or LLM_ALLOW_NO_KEY),
        "model": "demo" if DEMO_MODE or not (LLM_API_KEY or LLM_ALLOW_NO_KEY) else LLM_MODEL,
    }


@app.post("/api/roadmap")
async def create_roadmap(
    data: RoadmapRequest,
    request: Request,
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_api_csrf(request)
    check_rate_limit(client_key(request))

    if DEMO_MODE or not (LLM_API_KEY or LLM_ALLOW_NO_KEY):
        # Небольшая задержка, чтобы интерфейс прожил состояние загрузки.
        await asyncio.sleep(0.7)
        roadmap: Roadmap = demo_roadmap(data)
    else:
        assert request.app.state.http is not None
        roadmap = await call_llm(data)

    payload = roadmap.model_dump()
    record = RoadmapRecord(
        user_id=user.id,
        prompt=data.prompt,
        level=data.level,
        pace=data.pace,
        horizon=data.horizon,
        title=roadmap.title,
        summary=roadmap.summary,
        payload=payload,
        done_tasks=[],
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return JSONResponse(
        {
            **payload,
            "id": record.id,
            "done_tasks": [],
            "stats": roadmap_stats(payload, []),
        }
    )


@app.put("/api/roadmaps/{roadmap_id}/progress")
async def update_roadmap_progress(
    roadmap_id: int,
    data: ProgressUpdate,
    request: Request,
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_api_csrf(request)

    record = db.get(RoadmapRecord, roadmap_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Roadmap не найден.")

    payload = record.payload if isinstance(record.payload, dict) else {}
    done_tasks = filter_done_tasks(payload, data.done_tasks)
    record.done_tasks = done_tasks
    db.commit()

    return {
        "done_tasks": done_tasks,
        "stats": roadmap_stats(payload, done_tasks),
    }
