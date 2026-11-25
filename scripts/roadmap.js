/* ============================================================
   Roadly — страница roadmap: прогресс в БД, экспорт в Markdown
   ============================================================ */
(() => {
    "use strict";

    const dataEl = document.getElementById("roadmapData");
    const card = document.getElementById("progressCard");
    const timeline = document.getElementById("timeline");
    if (!dataEl || !card || !timeline) return;

    let roadmap = {};
    try {
        roadmap = JSON.parse(dataEl.textContent || "{}") || {};
    } catch {
        roadmap = {};
    }

    const progressUrl = card.dataset.progressUrl || "";
    const exportUrl = card.dataset.exportUrl || "";
    const csrfToken = card.dataset.csrf || "";

    const bar = document.getElementById("progressBar");
    const label = document.getElementById("progressLabel");
    const note = document.getElementById("progressNote");
    const toast = document.getElementById("toast");

    let saveTimer = null;
    let saving = false;
    let dirty = false;
    let toastTimer = null;

    function showToast(message) {
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add("is-visible");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2400);
    }

    function redirectToLogin() {
        const next = encodeURIComponent(window.location.pathname);
        window.location.assign(`/login?next=${next}`);
    }

    function checkedIds() {
        return Array.from(timeline.querySelectorAll('input[data-task-id]:checked')).map(
            (input) => input.dataset.taskId
        );
    }

    function totalTasks() {
        return timeline.querySelectorAll("input[data-task-id]").length;
    }

    function plural(count, one, few, many) {
        const mod10 = count % 10;
        const mod100 = count % 100;
        if (mod10 === 1 && mod100 !== 11) return one;
        if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
        return many;
    }

    function updateProgress() {
        const total = totalTasks();
        const done = checkedIds().length;
        const percent = total === 0 ? 0 : Math.round((done / total) * 100);

        if (bar) bar.style.width = `${percent}%`;
        if (label) label.textContent = `${percent}%`;
        if (note) {
            note.textContent =
                total === 0
                    ? "В этом roadmap пока нет задач."
                    : done === total
                      ? `Все ${total} ${plural(total, "задача", "задачи", "задач")} выполнены — отличная работа!`
                      : `Выполнено ${done} из ${total}. Отмечайте задачи — прогресс сохраняется в аккаунте.`;
            note.classList.toggle("is-complete", total > 0 && done === total);
        }

        timeline.querySelectorAll(".phase").forEach((phaseEl) => {
            const boxes = Array.from(phaseEl.querySelectorAll("input[data-task-id]"));
            const allDone = boxes.length > 0 && boxes.every((box) => box.checked);
            const marker = phaseEl.querySelector(".phase-marker");
            const phaseCard = phaseEl.querySelector(".phase-card");
            if (marker) marker.classList.toggle("is-done", allDone);
            if (phaseCard) phaseCard.classList.toggle("is-done", allDone);
        });
    }

    async function saveProgress() {
        if (!progressUrl) return;
        if (saving) {
            dirty = true;
            return;
        }

        saving = true;
        dirty = false;
        try {
            const response = await fetch(progressUrl, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                    "X-CSRF-Token": csrfToken,
                },
                body: JSON.stringify({ done_tasks: checkedIds() }),
            });

            if (response.status === 401) {
                redirectToLogin();
                return;
            }
            if (!response.ok) {
                showToast("Не удалось сохранить прогресс. Попробуйте ещё раз.");
            }
        } catch {
            showToast("Не удалось сохранить прогресс. Проверьте соединение.");
        } finally {
            saving = false;
            if (dirty) {
                dirty = false;
                saveProgress();
            }
        }
    }

    function scheduleSave() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveProgress, 350);
    }

    timeline.addEventListener("change", (event) => {
        if (!event.target.matches('input[data-task-id]')) return;
        updateProgress();
        scheduleSave();
    });

    updateProgress();

    /* ------------------------------------------------------------
       Экспорт
       ------------------------------------------------------------ */
    function slugify(text) {
        return (
            String(text || "")
                .toLowerCase()
                .replace(/[^a-zа-яё0-9]+/gi, "-")
                .replace(/^-+|-+$/g, "")
                .slice(0, 60) || "roadmap"
        );
    }

    async function fetchMarkdown() {
        if (!exportUrl) throw new Error("export-unavailable");
        const response = await fetch(exportUrl, { headers: { Accept: "text/markdown" } });
        if (response.status === 401) {
            redirectToLogin();
            throw new Error("auth");
        }
        if (!response.ok) throw new Error("export-failed");
        return response.text();
    }

    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch {
            const area = document.createElement("textarea");
            area.value = text;
            area.setAttribute("readonly", "");
            area.style.position = "fixed";
            area.style.opacity = "0";
            document.body.appendChild(area);
            area.select();
            let copied = false;
            try {
                copied = document.execCommand("copy");
            } catch {
                copied = false;
            }
            area.remove();
            return copied;
        }
    }

    const copyBtn = document.getElementById("copyBtn");
    const downloadBtn = document.getElementById("downloadBtn");

    if (copyBtn) {
        copyBtn.addEventListener("click", async () => {
            try {
                const markdown = await fetchMarkdown();
                showToast((await copyText(markdown)) ? "Скопировано в Markdown" : "Не удалось скопировать");
            } catch (error) {
                if (error.message !== "auth") showToast("Не удалось получить Markdown");
            }
        });
    }

    if (downloadBtn) {
        downloadBtn.addEventListener("click", async () => {
            try {
                const markdown = await fetchMarkdown();
                const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = `${slugify(roadmap.title)}.md`;
                document.body.appendChild(link);
                link.click();
                link.remove();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
                showToast("Файл скачан");
            } catch (error) {
                if (error.message !== "auth") showToast("Не удалось скачать Markdown");
            }
        });
    }
})();
