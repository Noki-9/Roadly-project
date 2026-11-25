from __future__ import annotations

import logging
import re
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User

logger = logging.getLogger("uvicorn.error")

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72

DUMMY_PASSWORD_HASH = bcrypt.hashpw(
    b"roadly-dummy-password", bcrypt.gensalt(rounds=12)
).decode("ascii")

def normalize_email(value: str) -> str:
    return value.strip().lower()

def validate_email(value: str) -> str | None:
    if not value or len(value) > 254 or not EMAIL_RE.fullmatch(value):
        return "Введите корректный email."
    return None

def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Пароль должен содержать минимум {MIN_PASSWORD_LENGTH} символов."
    if "\x00" in password:
        return "Пароль содержит недопустимый символ."
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return "Пароль слишком длинный: максимум 72 байта."
    return None

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))

def get_current_user(request: Request, db: Session) -> User | None:
    raw_id = request.session.get("user_id")
    try:
        user_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    if user_id <= 0:
        return None
    return db.get(User, user_id)

def login_user(request: Request, user: User) -> None:
    """Новая сессия после входа — защита от session fixation, но CSRF-токен сохраняем."""
    current_csrf = request.session.get("csrf_token")
    request.session.clear()
    request.session["user_id"] = user.id
    
    if current_csrf:
        request.session["csrf_token"] = current_csrf
    else:
        ensure_csrf(request)

def logout_user(request: Request) -> None:
    request.session.clear()

def ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not isinstance(token, str) or len(token) < 24:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token

def csrf_valid(request: Request, token: str | None) -> bool:
    expected = request.session.get("csrf_token")
    return (
        isinstance(expected, str)
        and isinstance(token, str)
        and bool(token)
        and secrets.compare_digest(expected, token)
    )

def verify_csrf(request: Request, token: str | None) -> None:
    if not csrf_valid(request, token):
        expected = request.session.get("csrf_token")
        logger.warning(
            f"CSRF FAIL! Path: {request.url.path}. "
            f"Session token: {expected}, Header token: {token}. "
            f"Cookies: {request.cookies}"
        )
        raise HTTPException(
            status_code=400,
            detail="Ошибка проверки безопасности. Обновите страницу и попробуйте снова.",
        )

def verify_api_csrf(request: Request) -> None:
    verify_csrf(request, request.headers.get("x-csrf-token"))

def require_api_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт.")
    return user

def safe_next(value: str | None, default: str = "/dashboard") -> str:
    if not value:
        return default
    value = value.strip()
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "\n" in value
        or "\r" in value
    ):
        return default
    return value

def add_flash(request: Request, message: str, kind: str = "success") -> None:
    flashes = request.session.get("_flashes")
    if not isinstance(flashes, list):
        flashes = []
    flashes.append({"message": message, "kind": kind})
    request.session["_flashes"] = flashes[-6:]

def pop_flashes(request: Request) -> list[dict[str, str]]:
    flashes = request.session.pop("_flashes", [])
    if not isinstance(flashes, list):
        return []
    return [item for item in flashes if isinstance(item, dict) and item.get("message")]