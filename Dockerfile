# syntax=docker/dockerfile:1

# ---- Runtime ---------------------------------------------------------------
FROM python:3.13-slim

# Не создавать .pyc, не буферизовать логи, не хранить кэш pip в образе.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_URL=sqlite:////app/data/roadly.db

WORKDIR /app

# 1. Зависимости отдельным слоем: пересобираются только при изменении
#    requirements.txt, а не при каждом изменении кода.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 2. Код приложения. .env сюда НЕ копируется — секреты передаются
#    через переменные окружения (см. docker-compose.yml).
COPY main.py check_llm.py ./
COPY core ./core
COPY llm ./llm
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts

# 3. Непривилегированный пользователь и каталог для файла SQLite.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin roadly \
    && mkdir -p /app/data \
    && chown -R roadly:roadly /app

USER roadly

EXPOSE 8000

# Docker сам проверяет, что приложение отвечает на /api/health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

# Один процесс uvicorn: для SQLite это безопаснее, чем несколько воркеров.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
