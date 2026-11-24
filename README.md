# Roadly — AI-генератор roadmap

Веб-приложение: пользователь описывает цель, а LLM на бэкенде собирает пошаговый
roadmap с этапами, задачами, сроками и результатами. Работает с любым
OpenAI-совместимым API; ключ (если он нужен) живёт только на сервере и никогда
не передаётся в браузер.

## Что внутри

```
main.py                 FastAPI: страница, /api/roadmap, вызов LLM
templates/index.html    разметка интерфейса
static/styles.css       стили (светлая/тёмная тема, адаптив)
scripts/app.js          генерация, рендер, прогресс, экспорт в Markdown
check_llm.py            проверка провайдера без вывода ключа
.env.example            пример конфигурации
requirements.txt        зависимости
```

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

#необхадимо также создать файл .env и указать в нем API ключ для нее

uvicorn main:app --reload
```

Откройте http://127.0.0.1:8000.

Проверить провайдера, не запуская сайт:

```bash
.venv/bin/python scripts/check_llm.py
```

Скрипт не печатает ключ целиком и сообщает, принят ли он провайдером, какая
модель доступна и в чём причина ошибки (неверный ключ, лимит, блокировка региона).

## Провайдеры

| Вариант                  | Ключ      | Доступность из РФ | Ограничения                     |
| ------------------------ | --------- | ----------------- | ------------------------------- |
| **Pollinations** (по умолчанию) | не нужен  | да                | 1 запрос / 45 сек с одного IP   |
| DeepSeek                 | нужен     | да                | платно, недорого                |
| SambaNova                | нужен     | да                | бесплатный тариф с лимитами     |
| VseGPT / ProxyAPI        | нужен     | да                | бесплатные кредиты / платно     |
| OpenAI, OpenRouter       | нужен     | **нет**, HTTP 403 | нужен VPN или `HTTPS_PROXY`     |
| Ollama (локально)        | не нужен  | да                | скорость зависит от CPU         |

### Pollinations — бесплатно и без ключа

В `.env` по умолчанию:

```env
LLM_CHAT_URL=https://text.pollinations.ai/openai
LLM_MODEL=openai
LLM_ALLOW_NO_KEY=1
LLM_TIMEOUT=120
```

Это модель GPT-OSS 20B, доступная из РФ. Бесплатный тариф ограничен одним
запросом в 45 секунд с IP; при превышении бэкенд возвращает `429` с
`Retry-After`, а интерфейс показывает понятное сообщение. Для личных тестов
этого достаточно; для нагрузки нужен ключ или локальная модель.

### Свой ключ

```env
LLM_CHAT_URL=https://api.deepseek.com/v1/chat/completions
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
LLM_ALLOW_NO_KEY=0
```

Подойдёт любой OpenAI-совместимый `/chat/completions`. Для OpenRouter нужен VPN
или прокси: провайдер отдаёт `403 Access denied by security policy` по IP из РФ.

### OpenRouter через прокси

```env
LLM_CHAT_URL=https://openrouter.ai/api/v1/chat/completions
LLM_API_KEY=sk-or-v1-...
LLM_MODEL=openai/gpt-4o-mini
LLM_ALLOW_NO_KEY=0
HTTPS_PROXY=http://127.0.0.1:1080
```

`httpx` читает `HTTPS_PROXY` из окружения автоматически.

### Локальная Ollama

Если нужны неограниченные бесплатные генерации без интернета:

```bash
curl -L https://ollama.com/download/ollama-linux-amd64.tgz | tar -xz -C ~/.local/ollama
~/.local/ollama/bin/ollama serve
~/.local/ollama/bin/ollama pull qwen2.5:3b-instruct
```

```env
LLM_CHAT_URL=http://127.0.0.1:11434/v1/chat/completions
LLM_MODEL=qwen2.5:3b-instruct
LLM_ALLOW_NO_KEY=1
LLM_TIMEOUT=300
LLM_BASE_URL=http://127.0.0.1:11434/v1
```

На CPU генерация занимает 1–2 минуты; включите `LLM_TIMEOUT=300`.

## Настройки (.env)

| Переменная        | По умолчанию                | Назначение                                        |
| ----------------- | --------------------------- | ------------------------------------------------- |
| `LLM_CHAT_URL`    | `{LLM_BASE_URL}/chat/completions` | Полный URL chat completions                 |
| `LLM_API_KEY`     | —                           | Ключ провайдера (необязателен для бесплатных)     |
| `LLM_BASE_URL`    | `https://api.openai.com/v1` | Базовый URL (для проверки `/models`)              |
| `LLM_MODEL`       | `gpt-4o-mini`               | Имя модели                                        |
| `LLM_ALLOW_NO_KEY`| `0`                         | Разрешить работу без ключа (Pollinations, Ollama) |
| `LLM_TIMEOUT`     | `90`                        | Таймаут запроса к модели, секунды                 |
| `ROADLY_DEMO`     | `0`                         | `1` — всегда демо-режим, без вызовов LLM          |
| `SESSION_SECRET`  | `dev-secret-change-me`      | Секрет cookie-сессий, задайте свой в проде         |

Без ключа и без `LLM_ALLOW_NO_KEY` приложение работает в **демо-режиме**:
интерфейс полностью функционален, но возвращается пример roadmap с пометкой
«Демо-режим».

## API

`POST /api/roadmap`

```json
{
  "prompt": "Хочу стать junior frontend-разработчиком за 6 месяцев",
  "level": "новичок",
  "pace": "сбалансированный",
  "horizon": "6 месяцев"
}
```

Ответ — структурированный JSON: `title`, `summary`, `duration`, `level`,
`phases[]` (с `tasks` и `outcome`), `skills[]`, `resources[]`, `demo`.

`GET /api/health` — статус и признак демо-режима (удобно для проверки настройки ключа).

## Возможности интерфейса

- генерация roadmap по свободному промпту и параметрам (уровень, темп, горизонт);
- примеры запросов в один клик, `Ctrl/Cmd + Enter` для запуска;
- таймлайн этапов с чек-листом задач и живым прогрессом;
- сохранение roadmap и отметок в `localStorage` — можно закрыть страницу;
- экспорт в Markdown (копирование и скачивание);
- светлая/тёмная тема с учётом системной настройки;
- адаптивная вёрстка и корректная работа с клавиатуры;
- понятные ошибки: таймаут, неверный ключ, лимиты, пустой ответ модели.

## Замечания по безопасности

- ключ читается из окружения только в `main.py`, в HTML/JS его нет;
- промпт валидируется по длине, ответ модели нормализуется и проверяется через Pydantic;
- ссылки ресурсов допускаются только с `http://` и `https://`, вставка HTML экранируется;
- есть простой лимит: 6 запросов в минуту с одного IP (in-memory, для одного процесса);
- для продакшена задайте `SESSION_SECRET`, включите HTTPS и при необходимости
  замените in-memory лимитер на Redis.
