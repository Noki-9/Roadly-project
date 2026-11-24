import json
import re
from typing import Any

import httpx
from fastapi import HTTPException

from core.pydantic_models import Phase, Resource, Roadmap, RoadmapRequest
from main import LLM_API_KEY, LLM_CHAT_URL, LLM_MODEL
from main import app

with open('core/system_prompt.txt', 'r', encoding='utf-8') as file:
    SYSTEM_PROMPT = file.read()
    file.close()

def build_user_prompt(data: RoadmapRequest) -> str:
    return (
        f"Цель пользователя: {data.prompt}\n"
        f"Текущий уровень: {data.level}\n"
        f"Темп занятий: {data.pace}\n"
        f"Желаемый горизонт: {data.horizon}\n\n"
        "Составь roadmap в соответствии со схемой JSON. Ответь на русском языке."
    )


# ---------------------------------------------------------------------------
# LLM-вызов
# ---------------------------------------------------------------------------
def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("Модель вернула ответ, который не удалось разобрать как JSON.")


async def call_llm(request: RoadmapRequest) -> Roadmap:
    payload: dict[str, Any] = {
        "model": LLM_MODEL,
        "temperature": 0.6,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(request)},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    http: httpx.AsyncClient = app.state.http
    url = LLM_CHAT_URL

    try:
        response = await http.post(url, headers=headers, json=payload)

        # Некоторые провайдеры не поддерживают response_format — повторяем без него.
        if response.status_code == 400 and "response_format" in response.text:
            payload.pop("response_format", None)
            response = await http.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Модель не ответила вовремя. Попробуйте ещё раз или упростите запрос.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Не удалось связаться с LLM. Проверьте LLM_CHAT_URL и доступ к сети на сервере.",
        ) from exc

    if response.status_code == 402:
        retry_after = response.headers.get("retry-after", "").strip()
        detail = "Лимит бесплатного тарифа провайдера исчерпан."
        if retry_after:
            detail = f"{detail} Повторите примерно через {retry_after} сек."
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": retry_after} if retry_after else None,
        )
    if response.status_code == 401:
        raise HTTPException(status_code=502, detail="LLM отклонил API-ключ. Проверьте LLM_API_KEY на сервере.")
    if response.status_code == 429:
        retry_after = response.headers.get("retry-after", "").strip()
        detail = "Слишком много запросов к LLM."
        if retry_after:
            detail = f"{detail} Повторите примерно через {retry_after} сек."
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": retry_after} if retry_after else None,
        )
    if response.status_code == 503:
        raise HTTPException(status_code=503, detail="Провайдер временно перегружен. Попробуйте через минуту.")
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"LLM вернул ошибку {response.status_code}. Попробуйте ещё раз чуть позже.",
        )

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Неожиданный формат ответа от LLM.") from exc

    if isinstance(content, list):  # некоторые провайдеры отдают массив частей
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))

    try:
        raw = extract_json(str(content))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Не удалось разобрать roadmap от модели. Попробуйте ещё раз.") from exc

    # Мягкая нормализация: модель может вернуть лишние поля или строки.
    raw.setdefault("title", "Ваш персональный roadmap")
    raw.setdefault("duration", request.horizon)
    raw.setdefault("level", request.level)

    phases = raw.get("phases")
    if not isinstance(phases, list) or not phases:
        raise HTTPException(status_code=502, detail="Модель вернула roadmap без этапов. Попробуйте переформулировать запрос.")

    normalized_phases = []
    for index, phase in enumerate(phases[:10]):
        if not isinstance(phase, dict):
            continue
        tasks = phase.get("tasks", [])
        if isinstance(tasks, str):
            tasks = [tasks]
        if not isinstance(tasks, list):
            tasks = []
        normalized_tasks: list[str] = []
        for task in tasks:
            if isinstance(task, dict):
                task_text = task.get("title") or task.get("text") or ""
            else:
                task_text = task
            task_text = str(task_text).strip()
            if task_text:
                normalized_tasks.append(task_text[:300])

        normalized_phases.append(
            {
                "title": str(phase.get("title") or f"Этап {index + 1}")[:160],
                "duration": str(phase.get("duration") or "")[:60],
                "description": str(phase.get("description") or "")[:600],
                "tasks": normalized_tasks[:8],
                "outcome": str(phase.get("outcome") or phase.get("result") or "")[:400],
            }
        )

    if not normalized_phases:
        raise HTTPException(status_code=502, detail="Модель вернула roadmap без этапов. Попробуйте ещё раз.")

    normalized_resources = []
    for item in raw.get("resources", [])[:6] if isinstance(raw.get("resources"), list) else []:
        if isinstance(item, str):
            normalized_resources.append({"title": item[:160], "url": ""})
        elif isinstance(item, dict) and item.get("title"):
            url = str(item.get("url") or "")
            if url and not re.match(r"^https?://", url):
                url = ""
            normalized_resources.append({"title": str(item["title"])[:160], "url": url[:500]})

    return Roadmap(
        title=str(raw.get("title") or "Ваш персональный roadmap")[:160],
        summary=str(raw.get("summary") or raw.get("goal") or "")[:800],
        duration=str(raw.get("duration") or request.horizon)[:60],
        level=str(raw.get("level") or request.level)[:60],
        phases=[Phase(**phase) for phase in normalized_phases],
        skills=[str(skill)[:100] for skill in raw.get("skills", [])[:12] if str(skill).strip()]
        if isinstance(raw.get("skills"), list)
        else [],
        resources=[Resource(**item) for item in normalized_resources],
        demo=False,
    )