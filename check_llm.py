#!/usr/bin/env python
"""
Проверка провайдера LLM без вывода ключа.

Использование:
    .venv/bin/python scripts/check_llm.py

Коды выхода:
    0 — провайдер доступен и готов к работе (ключ принят или не требуется)
    1 — ключ не настроен
    2 — ключ отклонён (401/403)
    3 — сеть / регион / конфигурация
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"


def load_env() -> None:
    if not ENV_PATH.is_file():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def mask(key: str) -> str:
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:6]}…{key[-4:]} ({len(key)} символов)"


def fail(code: int, message: str) -> None:
    print(f"✗ {message}")
    sys.exit(code)


def is_region_block(text: str) -> bool:
    """403 от Cloudflare/провайдера из-за страны или IP, а не из-за ключа."""
    low = text.lower()
    return any(
        marker in low
        for marker in (
            "security policy",
            "unsupported_country",
            "country, region",
            "territory not supported",
        )
    )


def main() -> None:
    load_env()

    key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    base_url = (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    chat_url = (os.getenv("LLM_CHAT_URL") or f"{base_url}/chat/completions").strip()
    model = os.getenv("LLM_MODEL") or "gpt-4o-mini"
    allow_no_key = os.getenv("LLM_ALLOW_NO_KEY", "").lower() in {"1", "true", "yes", "on"}

    print(f"Провайдер:  {chat_url}")
    print(f"Модель:     {model}")

    if not key and not allow_no_key:
        print("Ключ:       не задан")
        fail(1, "Ключ не найден. Укажите LLM_API_KEY в .env — сейчас работает демо-режим.")

    headers = {"Content-Type": "application/json"}
    if key:
        print(f"Ключ:       {mask(key)}")
        headers["Authorization"] = f"Bearer {key}"
    else:
        print("Ключ:       не требуется (LLM_ALLOW_NO_KEY=1)")

    safe = lambda text: text.replace(key, mask(key)) if key else str(text)

    try:
        with httpx.Client(timeout=60.0) as client:
            if key:
                models = client.get(f"{base_url}/models", headers=headers)
                if models.status_code == 200:
                    try:
                        ids = [m.get("id") for m in models.json().get("data", []) if isinstance(m, dict)]
                        available = model in ids
                        print(f"Модели:     доступно {len(ids)}; {model} {'найдена' if available else 'не найдена в списке'}")
                    except (ValueError, AttributeError):
                        print("Модели:     список получен")
                    print("✓ Ключ принят провайдером.")
                    return
                if models.status_code in (401, 403):
                    if is_region_block(models.text):
                        fail(
                            3,
                            "Провайдер блокирует ваш регион/IP (HTTP 403), ключ при этом не проверен. "
                            "Включите VPN/прокси или выберите другого провайдера.",
                        )
                    fail(2, f"Ключ отклонён (HTTP {models.status_code}). Проверьте ключ и провайдера.")
                # Если /models не поддерживается, проверяем минимальным запросом к чату.

            check = client.post(
                chat_url,
                headers=headers,
                json={
                    "model": model,
                    "max_tokens": 20,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": "Ответь одним словом: работает"}],
                },
            )

            if check.status_code in (401, 403):
                if is_region_block(check.text):
                    fail(
                        3,
                        "Провайдер блокирует ваш регион/IP (HTTP 403). Смените провайдера или включите VPN.",
                    )
                fail(2, f"Ключ отклонён (HTTP {check.status_code}). Проверьте ключ и провайдера.")

            if check.status_code == 402:
                retry = check.headers.get("retry-after", "")
                suffix = f" Повторите через ~{retry} сек." if retry else ""
                print(f"✓ Провайдер доступен, но бесплатный лимит исчерпан.{suffix}")
                return

            if check.status_code == 503:
                print("✓ Сеть и конфигурация в порядке, но провайдер временно перегружен. Попробуйте позже.")
                return

            if check.status_code == 429:
                retry = check.headers.get("retry-after", "")
                suffix = f" через ~{retry} сек." if retry else ""
                print(f"✓ Провайдер доступен, но сейчас rate-limit. Повторите{suffix}")
                return

            if check.status_code >= 400:
                try:
                    err = check.json().get("error", {})
                    detail = err.get("message") if isinstance(err, dict) else str(err)
                except ValueError:
                    detail = check.text[:300]
                fail(3, f"Провайдер вернул HTTP {check.status_code}: {safe(str(detail))[:300]}")

            try:
                content = check.json()["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                fail(3, "Неожиданный формат ответа провайдера.")

            print(f"Ответ:      {str(content)[:80]!r}")
            print("✓ Провайдер работает и отвечает.")
    except httpx.TimeoutException:
        fail(3, "Таймаут запроса. Проверьте сеть или LLM_CHAT_URL.")
    except httpx.HTTPError as exc:
        fail(3, f"Сетевая ошибка: {exc.__class__.__name__}. Проверьте LLM_CHAT_URL и доступ к сети.")


if __name__ == "__main__":
    main()
