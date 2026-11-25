/* ============================================================
   Roadly — frontend logic
   ============================================================ */
(() => {
    "use strict";

    const DRAFT_KEY = "roadly:draft";
    const LEGACY_ROADMAP_KEY = "roadly:roadmap";
    const LEGACY_DONE_KEY = "roadly:done";

    const MAX_PROMPT = 800;

    const el = {
        form: document.getElementById("roadmapForm"),
        prompt: document.getElementById("prompt"),
        charCount: document.getElementById("charCount"),
        textareaWrap: document.querySelector(".textarea-wrap"),
        examples: document.getElementById("examples"),
        level: document.getElementById("level"),
        pace: document.getElementById("pace"),
        horizon: document.getElementById("horizon"),
        generateBtn: document.getElementById("generateBtn"),
        loadingPanel: document.getElementById("loadingPanel"),
        loadingStep: document.getElementById("loadingStep"),
        alert: document.getElementById("alert"),
        alertTitle: document.getElementById("alertTitle"),
        alertText: document.getElementById("alertText"),
        alertClose: document.getElementById("alertClose"),
        result: document.getElementById("result"),
        resultTitle: document.getElementById("resultTitle"),
        resultSummary: document.getElementById("resultSummary"),
        resultMeta: document.getElementById("resultMeta"),
        demoBadge: document.getElementById("demoBadge"),
        timeline: document.getElementById("timeline"),
        progressBar: document.getElementById("progressBar"),
        progressLabel: document.getElementById("progressLabel"),
        progressNote: document.getElementById("progressNote"),
        extras: document.getElementById("extras"),
        skillsCard: document.getElementById("skillsCard"),
        skillList: document.getElementById("skillList"),
        resourcesCard: document.getElementById("resourcesCard"),
        resourceList: document.getElementById("resourceList"),
        copyBtn: document.getElementById("copyBtn"),
        downloadBtn: document.getElementById("downloadBtn"),
        newBtn: document.getElementById("newBtn"),
        openSavedBtn: document.getElementById("openSavedBtn"),
        toast: document.getElementById("toast"),
    };

    const icons = {
        clock: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M12 7.5V12l3 2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        layers: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m12 3.5 8 4.3-8 4.2-8-4.2 8-4.3Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="m4 12 8 4.2 8-4.2M4 16.2l8 4.3 8-4.3" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
        target: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="4.5" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="1" fill="currentColor"/></svg>',
        tasks: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 6.5h11M9 12h11M9 17.5h11" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="m3.5 6.5 1.4 1.4L7 5.5M3.5 12l1.4 1.4L7 11M3.5 17.5l1.4 1.4L7 16.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        check: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        flag: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M6 21V4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M6 5h10.5l-1.8 3.5 1.8 3.5H6" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
        link: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10.5 13.5a3.5 3.5 0 0 0 5 0l2.5-2.5a3.54 3.54 0 0 0-5-5L11.5 7.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M13.5 10.5a3.5 3.5 0 0 0-5 0L6 13a3.54 3.54 0 0 0 5 5l1.5-1.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
    };

    const loadingSteps = [
        "Разбираем цель и контекст…",
        "Подбираем этапы и порядок…",
        "Оцениваем сроки и нагрузку…",
        "Формулируем задачи и результаты…",
        "Полируем финальный маршрут…",
    ];

    let currentRoadmap = null;
    let currentRoadmapId = null;
    let doneTasks = new Set();
    let loadingTimer = null;
    let toastTimer = null;
    let abortController = null;
    let progressTimer = null;
    const authenticated = document.body.dataset.authenticated === "true";
    const csrfToken =
        document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

    /* ------------------------------------------------------------
       Helpers
       ------------------------------------------------------------ */
    const escapeHtml = (value) =>
        String(value ?? "").replace(/[&<>"']/g, (ch) => {
            switch (ch) {
                case "&": return "&amp;";
                case "<": return "&lt;";
                case ">": return "&gt;";
                case '"': return "&quot;";
                case "'": return "&#39;";
                default: return ch;
            }
        });

    const isSafeUrl = (value) => {
        try {
            const url = new URL(value);
            return url.protocol === "http:" || url.protocol === "https:";
        } catch {
            return false;
        }
    };

    const showToast = (message) => {
        el.toast.textContent = message;
        el.toast.classList.add("is-visible");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.toast.classList.remove("is-visible"), 2400);
    };

    const saveDraft = (value) => {
        try {
            sessionStorage.setItem(DRAFT_KEY, value);
        } catch {
            /* storage may be unavailable (private mode) */
        }
    };

    function restoreDraft() {
        try {
            const draft = sessionStorage.getItem(DRAFT_KEY);
            sessionStorage.removeItem(DRAFT_KEY);
            if (draft) {
                el.prompt.value = draft;
                updateCharCount();
            }
        } catch {
            /* noop */
        }
    }

    function goToLogin() {
        saveDraft(el.prompt.value);
        window.location.assign(`/login?next=${encodeURIComponent("/#generator")}`);
    }

    /* ------------------------------------------------------------
       Prompt UX
       ------------------------------------------------------------ */
    function updateCharCount() {
        el.charCount.textContent = String(el.prompt.value.length);
        el.charCount.style.color =
            el.prompt.value.length > MAX_PROMPT * 0.9 ? "var(--danger)" : "";
    }

    el.prompt.addEventListener("input", () => {
        updateCharCount();
        el.textareaWrap.classList.remove("is-invalid");
    });

    el.examples.addEventListener("click", (event) => {
        const chip = event.target.closest(".chip");
        if (!chip) return;
        el.prompt.value = chip.dataset.prompt || "";
        el.prompt.focus();
        el.prompt.setSelectionRange(el.prompt.value.length, el.prompt.value.length);
        updateCharCount();
        el.textareaWrap.classList.remove("is-invalid");
    });

    document.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            el.form.requestSubmit();
        }
    });

    /* ------------------------------------------------------------
       Loading / errors
       ------------------------------------------------------------ */
    function startLoading() {
        let step = 0;
        el.loadingStep.textContent = loadingSteps[0];
        el.loadingPanel.hidden = false;
        el.generateBtn.disabled = true;
        el.generateBtn.classList.add("is-loading");
        el.generateBtn.querySelector(".btn-label").textContent = "Генерируем…";

        clearInterval(loadingTimer);
        loadingTimer = setInterval(() => {
            step = (step + 1) % loadingSteps.length;
            el.loadingStep.textContent = loadingSteps[step];
        }, 2800);
    }

    function stopLoading() {
        clearInterval(loadingTimer);
        loadingTimer = null;
        el.loadingPanel.hidden = true;
        el.generateBtn.disabled = false;
        el.generateBtn.classList.remove("is-loading");
        el.generateBtn.querySelector(".btn-label").textContent = "Сгенерировать roadmap";
    }

    function showError(title, message) {
        el.alertTitle.textContent = title;
        el.alertText.textContent = message;
        el.alert.hidden = false;
        el.alert.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function hideError() {
        el.alert.hidden = true;
    }

    el.alertClose.addEventListener("click", hideError);

    /* ------------------------------------------------------------
       Generation
       ------------------------------------------------------------ */
    el.form.addEventListener("submit", async (event) => {
        event.preventDefault();
        hideError();

        const prompt = el.prompt.value.trim();
        if (prompt.length < 10) {
            el.textareaWrap.classList.add("is-invalid");
            el.prompt.focus();
            showError(
                "Опишите цель подробнее",
                "Добавьте пару деталей: чему хотите научиться, за какой срок и сколько времени есть в неделю."
            );
            return;
        }

        if (!authenticated) {
            goToLogin();
            return;
        }

        if (abortController) abortController.abort();
        abortController = new AbortController();
        const timeout = setTimeout(() => abortController.abort(), 90_000);

        startLoading();
        if (el.result) el.result.hidden = true;

        try {
            const response = await fetch("/api/roadmap", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                    "X-CSRF-Token": csrfToken,
                },
                body: JSON.stringify({
                    prompt,
                    level: el.level.value,
                    pace: el.pace.value,
                    horizon: el.horizon.value,
                }),
                signal: abortController.signal,
            });

            if (response.status === 401) {
                goToLogin();
                return;
            }

            let payload = null;
            try {
                payload = await response.json();
            } catch {
                payload = null;
            }

            if (!response.ok) {
                const detail =
                    (payload && (payload.detail || payload.message)) ||
                    `Сервис ответил с ошибкой ${response.status}. Попробуйте ещё раз.`;
                throw new Error(
                    Array.isArray(detail) ? "Проверьте параметры запроса и попробуйте снова." : detail
                );
            }

            if (!payload || !Array.isArray(payload.phases) || payload.phases.length === 0) {
                throw new Error("Модель вернула пустой roadmap. Попробуйте переформулировать запрос.");
            }

            currentRoadmap = normalizeRoadmap(payload);
            currentRoadmapId = payload.id ? Number(payload.id) : null;
            doneTasks = new Set();
            renderRoadmap(currentRoadmap);

            if (el.openSavedBtn) {
                if (currentRoadmapId) {
                    el.openSavedBtn.href = `/roadmaps/${currentRoadmapId}`;
                    el.openSavedBtn.hidden = false;
                } else {
                    el.openSavedBtn.hidden = true;
                }
            }

            el.result.hidden = false;
            el.result.scrollIntoView({ behavior: "smooth", block: "start" });
            showToast("Roadmap готов — сохранён в кабинете 🎉");
        } catch (error) {
            if (error.name === "AbortError") {
                showError(
                    "Превышено время ожидания",
                    "Генерация заняла больше 90 секунд. Попробуйте ещё раз или упростите запрос."
                );
            } else if (error.message.includes("Ошибка проверки безопасности") || error.message.includes("Сессия устарела")) {
                showError(
                    "Сессия устарела",
                    "Обновляем страницу для синхронизации данных. Пожалуйста, подождите..."
                );
                setTimeout(() => window.location.reload(), 1500);
                return; // Прерываем выполнение, страница перезагрузится
            } else {
                showError("Не удалось создать roadmap", error.message || "Неизвестная ошибка.");
            }
            if (currentRoadmap) el.result.hidden = false;
        } finally {
            clearTimeout(timeout);
            stopLoading();
        }
    });

    /* ------------------------------------------------------------
       Normalization
       ------------------------------------------------------------ */
    function normalizeRoadmap(raw) {
        const phases = (Array.isArray(raw.phases) ? raw.phases : [])
            .map((phase, index) => ({
                title: String(phase.title || `Этап ${index + 1}`),
                duration: String(phase.duration || ""),
                description: String(phase.description || ""),
                tasks: (Array.isArray(phase.tasks) ? phase.tasks : [])
                    .map((task) => (typeof task === "string" ? task : task && task.title))
                    .filter(Boolean)
                    .map(String),
                outcome: String(phase.outcome || phase.result || ""),
            }))
            .filter((phase) => phase.title);

        const skills = (Array.isArray(raw.skills) ? raw.skills : [])
            .filter(Boolean)
            .map(String)
            .slice(0, 12);

        const resources = (Array.isArray(raw.resources) ? raw.resources : [])
            .map((item) => {
                if (typeof item === "string") return { title: item, url: "" };
                return { title: String(item.title || ""), url: String(item.url || "") };
            })
            .filter((item) => item.title)
            .slice(0, 8);

        return {
            title: String(raw.title || "Ваш персональный roadmap"),
            summary: String(raw.summary || raw.goal || ""),
            duration: String(raw.duration || ""),
            level: String(raw.level || ""),
            phases,
            skills,
            resources,
            demo: Boolean(raw.demo),
        };
    }

    /* ------------------------------------------------------------
       Rendering
       ------------------------------------------------------------ */
    function renderRoadmap(roadmap) {
        el.resultTitle.textContent = roadmap.title;
        el.resultSummary.textContent = roadmap.summary;
        el.resultSummary.hidden = !roadmap.summary;
        el.demoBadge.hidden = !roadmap.demo;

        const totalTasks = roadmap.phases.reduce((sum, phase) => sum + phase.tasks.length, 0);
        const meta = [];
        if (roadmap.duration) meta.push({ icon: icons.clock, text: roadmap.duration });
        if (roadmap.level) meta.push({ icon: icons.target, text: `Уровень: ${roadmap.level}` });
        meta.push({ icon: icons.layers, text: `${roadmap.phases.length} ${plural(roadmap.phases.length, "этап", "этапа", "этапов")}` });
        if (totalTasks) meta.push({ icon: icons.tasks, text: `${totalTasks} ${plural(totalTasks, "задача", "задачи", "задач")}` });

        el.resultMeta.innerHTML = meta
            .map((item) => `<span class="meta-pill">${item.icon}${escapeHtml(item.text)}</span>`)
            .join("");

        el.timeline.innerHTML = roadmap.phases
            .map((phase, phaseIndex) => renderPhase(phase, phaseIndex))
            .join("");

        renderSkills(roadmap.skills);
        renderResources(roadmap.resources);
        updateProgress();
    }

    function renderPhase(phase, phaseIndex) {
        const tasks = phase.tasks
            .map((task, taskIndex) => {
                const id = `${phaseIndex}:${taskIndex}`;
                return `
                    <label class="task">
                        <input type="checkbox" data-task-id="${id}" ${doneTasks.has(id) ? "checked" : ""}>
                        <span class="task-box">${icons.check}</span>
                        <span class="task-text">${escapeHtml(task)}</span>
                    </label>`;
            })
            .join("");

        const outcome = phase.outcome
            ? `<div class="outcome">${icons.flag}<span><strong>Результат этапа:</strong> ${escapeHtml(phase.outcome)}</span></div>`
            : "";

        return `
            <li class="phase" data-phase="${phaseIndex}" style="--delay: ${Math.min(phaseIndex, 8) * 60}ms">
                <div class="phase-marker" aria-hidden="true">${String(phaseIndex + 1).padStart(2, "0")}</div>
                <article class="phase-card">
                    <div class="phase-top">
                        <h3>${escapeHtml(phase.title)}</h3>
                        ${phase.duration ? `<span class="duration-pill">${icons.clock}${escapeHtml(phase.duration)}</span>` : ""}
                    </div>
                    ${phase.description ? `<p class="phase-desc">${escapeHtml(phase.description)}</p>` : ""}
                    ${tasks ? `<div class="task-list">${tasks}</div>` : ""}
                    ${outcome}
                </article>
            </li>`;
    }

    function renderSkills(skills) {
        if (!skills.length) {
            el.skillsCard.hidden = true;
            el.skillList.innerHTML = "";
        } else {
            el.skillsCard.hidden = false;
            el.skillList.innerHTML = skills
                .map((skill) => `<li>${escapeHtml(skill)}</li>`)
                .join("");
        }
        updateExtrasVisibility();
    }

    function renderResources(resources) {
        if (!resources.length) {
            el.resourcesCard.hidden = true;
            el.resourceList.innerHTML = "";
        } else {
            el.resourcesCard.hidden = false;
            el.resourceList.innerHTML = resources
                .map((resource) => {
                    if (resource.url && isSafeUrl(resource.url)) {
                        return `<li><a href="${escapeHtml(resource.url)}" target="_blank" rel="noopener noreferrer">${icons.link}${escapeHtml(resource.title)}</a></li>`;
                    }
                    return `<li><span class="resource-list-item">${icons.link}${escapeHtml(resource.title)}</span></li>`;
                })
                .join("");
        }
        updateExtrasVisibility();
    }

    function updateExtrasVisibility() {
        el.extras.hidden = el.skillsCard.hidden && el.resourcesCard.hidden;
    }

    /* ------------------------------------------------------------
       Progress
       ------------------------------------------------------------ */
    function updateProgress() {
        if (!currentRoadmap) return;

        const total = currentRoadmap.phases.reduce((sum, phase) => sum + phase.tasks.length, 0);
        const done = doneTasks.size;
        const percent = total === 0 ? 0 : Math.round((done / total) * 100);

        el.progressBar.style.width = `${percent}%`;
        el.progressLabel.textContent = `${percent}%`;
        el.progressNote.textContent =
            total === 0
                ? "В этом roadmap пока нет задач."
                : done === total
                  ? `Все ${total} ${plural(total, "задача", "задачи", "задач")} выполнены — отличная работа!`
                  : `Выполнено ${done} из ${total}. Отмечайте задачи — прогресс сохранится в аккаунте.`;
        el.progressNote.classList.toggle("is-complete", total > 0 && done === total);

        currentRoadmap.phases.forEach((phase, phaseIndex) => {
            const allDone =
                phase.tasks.length > 0 &&
                phase.tasks.every((_, taskIndex) => doneTasks.has(`${phaseIndex}:${taskIndex}`));
            const marker = el.timeline.querySelector(`[data-phase="${phaseIndex}"] .phase-marker`);
            const card = el.timeline.querySelector(`[data-phase="${phaseIndex}"] .phase-card`);
            if (marker) marker.classList.toggle("is-done", allDone);
            if (card) card.classList.toggle("is-done", allDone);
        });
    }

    el.timeline.addEventListener("change", (event) => {
        const checkbox = event.target.closest('input[type="checkbox"][data-task-id]');
        if (!checkbox) return;
        const id = checkbox.dataset.taskId;
        if (checkbox.checked) doneTasks.add(id);
        else doneTasks.delete(id);
        updateProgress();
        scheduleProgressSave();
    });

    /* ------------------------------------------------------------
       Persistence (база данных)
       ------------------------------------------------------------ */
    async function saveProgress() {
        if (!currentRoadmapId) return;
        try {
            const response = await fetch(`/api/roadmaps/${currentRoadmapId}/progress`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                    "X-CSRF-Token": csrfToken,
                },
                body: JSON.stringify({ done_tasks: Array.from(doneTasks) }),
            });

            if (response.status === 401) {
                goToLogin();
                return;
            }
            if (response.status === 400 || response.status === 403) {
                showToast("Сессия устарела. Обновляем страницу...");
                setTimeout(() => window.location.reload(), 1500);
                return;
            }
            if (!response.ok) {
                showToast("Не удалось сохранить прогресс. Попробуйте ещё раз.");
            }
        } catch {
            showToast("Не удалось сохранить прогресс. Проверьте соединение.");
        }
    }

    function scheduleProgressSave() {
        clearTimeout(progressTimer);
        progressTimer = setTimeout(saveProgress, 350);
    }

    /* ------------------------------------------------------------
       Export
       ------------------------------------------------------------ */
    function toMarkdown(roadmap) {
        const lines = [`# ${roadmap.title}`, ""];
        if (roadmap.summary) lines.push(roadmap.summary, "");
        if (roadmap.duration) lines.push(`**Срок:** ${roadmap.duration}`);
        if (roadmap.level) lines.push(`**Уровень:** ${roadmap.level}`);
        lines.push("");

        roadmap.phases.forEach((phase, index) => {
            lines.push(`## Этап ${index + 1}. ${phase.title}`);
            if (phase.duration) lines.push(`_${phase.duration}_`);
            lines.push("");
            if (phase.description) lines.push(phase.description, "");
            phase.tasks.forEach((task, taskIndex) => {
                const checked = doneTasks.has(`${index}:${taskIndex}`) ? "x" : " ";
                lines.push(`- [${checked}] ${task}`);
            });
            if (phase.tasks.length) lines.push("");
            if (phase.outcome) lines.push(`**Результат:** ${phase.outcome}`, "");
        });

        if (roadmap.skills.length) {
            lines.push("## Что вы освоите", "");
            roadmap.skills.forEach((skill) => lines.push(`- ${skill}`));
            lines.push("");
        }

        if (roadmap.resources.length) {
            lines.push("## Ресурсы", "");
            roadmap.resources.forEach((resource) => {
                if (resource.url && isSafeUrl(resource.url)) {
                    lines.push(`- [${resource.title}](${resource.url})`);
                } else {
                    lines.push(`- ${resource.title}`);
                }
            });
            lines.push("");
        }

        lines.push("---", "Сгенерировано в Roadly");
        return lines.join("\n");
    }

    function slugify(text) {
        return (
            text
                .toLowerCase()
                .replace(/[^a-zа-яё0-9]+/gi, "-")
                .replace(/^-+|-+$/g, "")
                .slice(0, 60) || "roadmap"
        );
    }

    async function copyMarkdown() {
        if (!currentRoadmap) return;
        const markdown = toMarkdown(currentRoadmap);
        try {
            await navigator.clipboard.writeText(markdown);
            showToast("Скопировано в Markdown");
        } catch {
            const area = document.createElement("textarea");
            area.value = markdown;
            area.setAttribute("readonly", "");
            area.style.position = "fixed";
            area.style.opacity = "0";
            document.body.appendChild(area);
            area.select();
            try {
                document.execCommand("copy");
                showToast("Скопировано в Markdown");
            } catch {
                showToast("Не удалось скопировать");
            }
            area.remove();
        }
    }

    function downloadMarkdown() {
        if (!currentRoadmap) return;
        const blob = new Blob([toMarkdown(currentRoadmap)], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${slugify(currentRoadmap.title)}.md`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        showToast("Файл скачан");
    }

    el.copyBtn.addEventListener("click", copyMarkdown);
    el.downloadBtn.addEventListener("click", downloadMarkdown);

    el.newBtn.addEventListener("click", () => {
        currentRoadmap = null;
        currentRoadmapId = null;
        doneTasks = new Set();
        if (el.openSavedBtn) el.openSavedBtn.hidden = true;
        el.result.hidden = true;
        el.prompt.value = "";
        updateCharCount();
        hideError();
        el.prompt.focus();
        document.getElementById("generator").scrollIntoView({ behavior: "smooth", block: "start" });
    });

    /* ------------------------------------------------------------
       Utils
       ------------------------------------------------------------ */
    function plural(count, one, few, many) {
        const mod10 = count % 10;
        const mod100 = count % 100;
        if (mod10 === 1 && mod100 !== 11) return one;
        if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
        return many;
    }

    /* ------------------------------------------------------------
       Boot
       ------------------------------------------------------------ */
    try {
        // Старые версии хранили roadmap в localStorage — данные переехали в БД.
        localStorage.removeItem(LEGACY_ROADMAP_KEY);
        localStorage.removeItem(LEGACY_DONE_KEY);
    } catch {
        /* noop */
    }
    updateCharCount();
    restoreDraft();
})();