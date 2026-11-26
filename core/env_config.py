import os
from pathlib import Path

# Корень проекта (на уровень выше папки core)
BASE_DIR = Path(__file__).resolve().parent.parent

def _load_dotenv(path: Path) -> None:
    """Минимальная загрузка .env без внешних зависимостей."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

# Загружаем .env ДО того, как начнем читать os.getenv()
_load_dotenv(BASE_DIR / ".env")

# --- Конфигурация LLM ---
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
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
DEMO_MODE = os.getenv("ROADLY_DEMO", "").lower() in {"1", "true", "yes", "on"}

# --- Конфигурация сессий ---
SESSION_SECRET = (os.getenv("SESSION_SECRET") or "").strip() or "dev-secret-change-me"
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "").lower() in {"1", "true", "yes", "on"}