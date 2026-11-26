# Roadly — AI-генератор roadmap

Веб-приложение: пользователь описывает цель, а LLM на бэкенде собирает пошаговый
roadmap с этапами, задачами, сроками и результатами. Roadmap и прогресс
сохраняются в базе данных и доступны в личном кабинете. Ключ LLM (если он нужен)
живёт только на сервере и никогда не передаётся в браузер.

## Что внутри

```
main.py                     FastAPI: страницы, авторизация, API, вызов LLM
core/database.py            подключение к БД, сессии SQLAlchemy, создание таблиц
core/models.py              модели User и RoadmapRecord
core/security.py            bcrypt, сессии, CSRF, проверка доступа
core/roadmap_utils.py       прогресс, Markdown-экспорт, подготовка данных для шаблонов
core/pydantic_models.py     валидация запросов и структуры roadmap
core/utilit.py              rate limiting по IP
templates/base.html         общий каркас страниц
templates/index.html        лендинг и генератор
templates/auth.html         вход и регистрация
templates/dashboard.html    личный кабинет со всеми roadmap
templates/roadmap.html      страница roadmap с чек-листом
static/styles.css           стили (редакционная сетка, светлая/тёмная тема, адаптив)
static/fonts/               self-hosted WOFF2: Literata и Golos Text (кириллица + латиница)
scripts/theme.js            тема, шапка, flash-сообщения, подтверждения
scripts/app.js              генерация, рендер, прогресс, экспорт на лендинге
scripts/roadmap.js          прогресс и экспорт на странице roadmap
check_llm.py                проверка провайдера без вывода ключа
.env.example                пример конфигурации
requirements.txt            зависимости
```

## Запуск

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# отредактируйте .env: провайдер LLM и SESSION_SECRET

uvicorn main:app --reload
```

Откройте http://127.0.0.1:8000, зарегистрируйте аккаунт и создайте первый
roadmap. Таблицы `users` и `roadmaps` создаются автоматически при старте.
По умолчанию используется SQLite-файл `roadly.db` в корне проекта.

Проверить провайдера, не запуская сайт:

```bash
.venv/bin/python check_llm.py
```

Скрипт не печатает ключ целиком и сообщает, принят ли он провайдером, какая
модель доступна и в чём причина ошибки (неверный ключ, лимит, блокировка региона).

## Аккаунты и база данных

- **Регистрация и вход** — email и пароль. Email нормализуется, пароль должен
  содержать минимум 8 символов.
- **Пароли** хранятся только как bcrypt-хеш с индивидуальной солью
  (`bcrypt`, cost 12). Открытый пароль в базу не попадает.
- **Сессии** — подписанные cookie через `SessionMiddleware`; после входа сессия
  пересоздаётся (защита от session fixation).
- **CSRF** — токен в сессии. Формы передают его в скрытом поле, API-запросы —
  в заголовке `X-CSRF-Token`.
- **Доступ** — личный кабинет и roadmap доступны только владельцу. Чужой
  roadmap возвращает `404`, а не `403`, чтобы не раскрывать его существование.
- **SQL-инъекции** — все запросы идут через SQLAlchemy ORM и параметризованы.
  Пользовательский ввод не подставляется в SQL-строки.
- **XSS** — Jinja2 экранирует HTML, JSON для JS передаётся через `tojson`,
  ссылки ресурсов допускаются только с `http://` и `https://`.

Схема данных:

```text
users
  id, email (unique), password_hash, created_at

roadmaps
  id, user_id -> users.id (ON DELETE CASCADE),
  prompt, level, pace, horizon,
  title, summary, payload (JSON), done_tasks (JSON),
  created_at, updated_at
```

`payload` хранит полную структуру roadmap от модели, `done_tasks` — список
идентификаторов выполненных задач вида `0:2`.

### PostgreSQL

Для продакшена можно использовать PostgreSQL:

```bash
pip install "psycopg[binary]"
```

```env
DATABASE_URL=postgresql+psycopg://roadly:password@127.0.0.1:5432/roadly
```

Для больших проектов вместо `create_all` стоит подключить Alembic и миграции.

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

| Переменная          | По умолчанию                | Назначение                                        |
| ------------------- | --------------------------- | ------------------------------------------------- |
| `LLM_CHAT_URL`      | `{LLM_BASE_URL}/chat/completions` | Полный URL chat completions                 |
| `LLM_API_KEY`       | —                           | Ключ провайдера (необязателен для бесплатных)     |
| `LLM_BASE_URL`      | `https://api.openai.com/v1` | Базовый URL (для проверки `/models`)              |
| `LLM_MODEL`         | `gpt-4o-mini`               | Имя модели                                        |
| `LLM_ALLOW_NO_KEY`  | `0`                         | Разрешить работу без ключа (Pollinations, Ollama) |
| `LLM_TIMEOUT`       | `90`                        | Таймаут запроса к модели, секунды                 |
| `ROADLY_DEMO`       | `0`                         | `1` — всегда демо-режим, без вызовов LLM          |
| `SESSION_SECRET`    | `dev-secret-change-me`      | Секрет cookie-сессий, обязательно задайте свой    |
| `SESSION_HTTPS_ONLY`| `0`                         | `1` — cookie сессии только по HTTPS               |
| `DATABASE_URL`      | `sqlite:///roadly.db`       | Строка подключения SQLAlchemy                     |

Без ключа и без `LLM_ALLOW_NO_KEY` приложение работает в **демо-режиме**:
интерфейс полностью функционален, но возвращается пример roadmap с пометкой
«Демо-режим». Демо-roadmap тоже сохраняется в личном кабинете.

## API

Для API нужна активная сессия и CSRF-токен из meta-тега страницы
(`X-CSRF-Token`). Без входа возвращается `401`.

`POST /api/roadmap`

```json
{
  "prompt": "Хочу стать junior frontend-разработчиком за 6 месяцев",
  "level": "новичок",
  "pace": "сбалансированный",
  "horizon": "6 месяцев"
}
```

Ответ — структурированный JSON: `id`, `title`, `summary`, `duration`, `level`,
`phases[]` (с `tasks` и `outcome`), `skills[]`, `resources[]`, `demo`, `stats`.
Roadmap сразу сохраняется в БД.

`PUT /api/roadmaps/{id}/progress`

```json
{ "done_tasks": ["0:0", "1:2"] }
```

Принимаются только существующие идентификаторы задач; мусор отбрасывается.
Возвращает `done_tasks` и актуальную статистику.

`GET /api/health` — статус и признак демо-режима.

Страницы: `/`, `/register`, `/login`, `/dashboard`, `/roadmaps/{id}`,
`/roadmaps/{id}/export.md`.

## Возможности интерфейса

- регистрация, вход и выход; личный кабинет со всеми roadmap пользователя;
- генерация roadmap по свободному промпту и параметрам (уровень, темп, горизонт);
- сохранение roadmap и отметок задач в базе данных;
- таймлайн этапов с чек-листом задач и живым прогрессом;
- удаление roadmap с подтверждением;
- экспорт в Markdown (копирование и скачивание);
- примеры запросов в один клик, `Ctrl/Cmd + Enter` для запуска;
- светлая/тёмная тема с учётом системной настройки;
- адаптивная вёрстка и корректная работа с клавиатуры;
- понятные ошибки: таймаут, неверный ключ, лимиты, пустой ответ модели.

## Замечания по безопасности

- ключ читается из окружения только в `main.py`, в HTML/JS его нет;
- пароли хешируются bcrypt; в БД нет открытых паролей;
- сессионные cookie: `HttpOnly`, `SameSite=Lax`, подпись `itsdangerous`;
  для HTTPS включите `SESSION_HTTPS_ONLY=1`;
- CSRF-токен проверяется для всех изменяющих форм и API-запросов;
- после входа сессия пересоздаётся, `next` допускает только локальные пути;
- для несуществующего email выполняется bcrypt-проверка-заглушка, чтобы по
  времени ответа нельзя было определить наличие аккаунта;
- промпт валидируется по длине, ответ модели нормализуется и проверяется через
  Pydantic; ссылки ресурсов допускаются только с `http://` и `https://`;
- есть лимит: 6 генераций в минуту с одного IP и 10 попыток входа/регистрации
  за 5 минут (in-memory, для одного процесса);
- для продакшена задайте `SESSION_SECRET`, включите HTTPS, `SESSION_HTTPS_ONLY=1`
  и при необходимости замените in-memory лимитер на Redis.

## Возможные улучшения

- подтверждение email и восстановление пароля;
- Alembic-миграции вместо автоматического `create_all`;
- смена пароля и удаление аккаунта;
- фоновые задачи для генерации с прогрессом в реальном времени.
