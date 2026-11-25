from __future__ import annotations

import re
from datetime import datetime

TASK_ID_RE = re.compile(r"^\d{1,2}:\d{1,2}$")


def _phases(payload: dict) -> list[dict]:
    phases = payload.get("phases") if isinstance(payload, dict) else None
    if not isinstance(phases, list):
        return []
    return [phase for phase in phases if isinstance(phase, dict)]


def valid_task_ids(payload: dict) -> set[str]:
    ids: set[str] = set()
    for phase_index, phase in enumerate(_phases(payload)):
        tasks = phase.get("tasks")
        if not isinstance(tasks, list):
            continue
        for task_index in range(len(tasks)):
            ids.add(f"{phase_index}:{task_index}")
    return ids


def filter_done_tasks(payload: dict, raw_tasks: list) -> list[str]:
    """Оставляем только существующие задачи; защита от мусора в JSON."""
    allowed = valid_task_ids(payload)
    result: list[str] = []
    for value in raw_tasks[:500]:
        if isinstance(value, str) and TASK_ID_RE.fullmatch(value) and value in allowed:
            result.append(value)
    return sorted(set(result), key=lambda item: (int(item.split(":")[0]), int(item.split(":")[1])))


def roadmap_stats(payload: dict, done_tasks: list | None) -> dict:
    allowed = valid_task_ids(payload)
    done = {task for task in (done_tasks or []) if isinstance(task, str) and task in allowed}
    total = len(allowed)
    percent = round(len(done) / total * 100) if total else 0
    return {
        "total": total,
        "done": len(done),
        "percent": percent,
        "phases": len(_phases(payload)),
    }


def build_view(payload: dict, done_tasks: list | None) -> dict:
    """Готовит данные roadmap для серверного шаблона."""
    done = {task for task in (done_tasks or []) if isinstance(task, str)}
    phases: list[dict] = []

    for phase_index, phase in enumerate(_phases(payload)):
        tasks = phase.get("tasks") if isinstance(phase.get("tasks"), list) else []
        view_tasks = []
        for task_index, task in enumerate(tasks):
            task_id = f"{phase_index}:{task_index}"
            view_tasks.append(
                {
                    "id": task_id,
                    "text": str(task)[:500],
                    "done": task_id in done,
                }
            )
        phases.append(
            {
                "index": phase_index,
                "title": str(phase.get("title") or f"Этап {phase_index + 1}"),
                "duration": str(phase.get("duration") or ""),
                "description": str(phase.get("description") or ""),
                "outcome": str(phase.get("outcome") or ""),
                "tasks": view_tasks,
                "all_done": bool(view_tasks) and all(task["done"] for task in view_tasks),
            }
        )

    skills = payload.get("skills") if isinstance(payload.get("skills"), list) else []
    resources = payload.get("resources") if isinstance(payload.get("resources"), list) else []

    view_resources = []
    for item in resources:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title:
            continue
        view_resources.append(
            {
                "title": title[:300],
                "url": url[:500] if url.startswith(("http://", "https://")) else "",
            }
        )

    return {
        "phases": phases,
        "skills": [str(skill) for skill in skills if str(skill).strip()],
        "resources": view_resources,
    }


def roadmap_to_markdown(payload: dict, done_tasks: list | None) -> str:
    done = set(done_tasks or [])
    title = str(payload.get("title") or "Roadmap")
    lines = [f"# {title}", ""]

    summary = str(payload.get("summary") or "")
    if summary:
        lines.extend([summary, ""])

    duration = str(payload.get("duration") or "")
    level = str(payload.get("level") or "")
    if duration:
        lines.append(f"**Срок:** {duration}")
    if level:
        lines.append(f"**Уровень:** {level}")
    if duration or level:
        lines.append("")

    for phase_index, phase in enumerate(_phases(payload)):
        lines.append(f"## Этап {phase_index + 1}. {phase.get('title', '')}")
        if phase.get("duration"):
            lines.append(f"_{phase['duration']}_")
            lines.append("")
        if phase.get("description"):
            lines.extend([str(phase["description"]), ""])
        tasks = phase.get("tasks") if isinstance(phase.get("tasks"), list) else []
        for task_index, task in enumerate(tasks):
            checked = "x" if f"{phase_index}:{task_index}" in done else " "
            lines.append(f"- [{checked}] {task}")
        if tasks:
            lines.append("")
        if phase.get("outcome"):
            lines.extend([f"**Результат:** {phase['outcome']}", ""])

    skills = payload.get("skills")
    if isinstance(skills, list) and skills:
        lines.extend(["## Что вы освоите", ""])
        lines.extend(f"- {skill}" for skill in skills)
        lines.append("")

    resources = payload.get("resources")
    if isinstance(resources, list) and resources:
        lines.extend(["## Ресурсы", ""])
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            url = str(resource.get("url") or "")
            title_text = str(resource.get("title") or "")
            if url.startswith(("http://", "https://")):
                lines.append(f"- [{title_text}]({url})")
            elif title_text:
                lines.append(f"- {title_text}")
        lines.append("")

    lines.extend(["---", "Сгенерировано в Roadly"])
    return "\n".join(lines)


def filename_slug(title: str) -> str:
    ascii_slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:50]
    return ascii_slug or "roadmap"


def format_date_ru(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%d.%m.%Y")
