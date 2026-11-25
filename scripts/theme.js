/* ============================================================
   Roadly — общие элементы интерфейса: тема, шапка, flash, подтверждения
   ============================================================ */
(() => {
    "use strict";

    const THEME_KEY = "roadly:theme";
    const html = document.documentElement;
    const toggle = document.getElementById("themeToggle");
    const header = document.querySelector(".site-header");

    function applyTheme(theme) {
        html.setAttribute("data-theme", theme);
        if (toggle) {
            toggle.setAttribute(
                "aria-label",
                theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"
            );
        }
    }

    function initialTheme() {
        try {
            const stored = localStorage.getItem(THEME_KEY);
            if (stored === "light" || stored === "dark") return stored;
        } catch {
            /* noop */
        }
        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }

    applyTheme(initialTheme());

    if (toggle) {
        toggle.addEventListener("click", () => {
            const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
            applyTheme(next);
            try {
                localStorage.setItem(THEME_KEY, next);
            } catch {
                /* noop */
            }
        });
    }

    if (header) {
        const syncHeader = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
        syncHeader();
        window.addEventListener("scroll", syncHeader, { passive: true });
    }

    document.addEventListener("click", (event) => {
        const close = event.target.closest("[data-flash-close]");
        if (!close) return;
        const flash = close.closest(".flash");
        const stack = flash ? flash.parentElement : null;
        if (flash) flash.remove();
        if (stack && stack.children.length === 0) stack.remove();
    });

    document.addEventListener("submit", (event) => {
        const form = event.target.closest("form[data-confirm]");
        if (!form) return;
        if (!window.confirm(form.dataset.confirm || "Продолжить?")) {
            event.preventDefault();
        }
    });
})();
