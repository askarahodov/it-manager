# Архитектура IT Manager

## Стек и обоснование
- **Backend**: Python FastAPI (async) — обеспечивает быстрый backend, мгновенную генерацию OpenAPI, легко интегрируется с async SSH/Ansible, хорошая совместимость с SQLAlchemy/Alembic.
- **ORM/миграции**: SQLAlchemy + Alembic — стандартный стек для PostgreSQL, позволяет точно моделировать домен и выполнять безопасные миграции.
- **Frontend**: React + TypeScript + Vite + кастомная библиотека компонентов в стиле Admin Dashboard (Сторонние компоненты можно заменить на готовые UI-kit, например, shadcn/ui, Mantine, Ant Design).
- **SSH в браузере**: WebSocket + xterm.js, FastAPI + WebSocket рядом с asyncssh.
- **Jobs/Scheduler**: отдельный воркер на Python (asyncio loops) + Redis очередь, запуск `ansible-playbook` в контейнере воркера; расписания (interval/cron) выполняются воркером.
- **Secrets**: значения шифруются AES-GCM и хранятся в базе; master key из env (ENV_MASTER_KEY), рассекречивание только для авторизованных действий; поддерживаются типы password/token/text и private_key с passphrase.
- **Auth**: JWT на основе FastAPI Users или свой модуль; RBAC роли (admin/user).
- **Документация/Observability**: OpenAPI + healthcheck + structured logging.

## ER-диаграмма (текст)
```
User 1---* Playbook
User 1---* JobRun
User 1---* Secret
GroupType (static/dynamic) + Group 1---* Host (через association)
Host *---1 Credential/Sсret
Playbook *---* Group (через PlaybookTarget)
Playbook *---* Host
JobRun *---1 Playbook
JobRun *---1 InventorySnapshot
Secret *---* PlaybookVariable
```

Сущности:
- **User**: id, email, password_hash, role, created_at
- **Host**: id, name, hostname, port, os_type, environment, tags, description, status, last_check, check_method (ping/tcp/ssh)
- **Group**: id, name, type, rule_json (для dynamic), hosts (m2m)
- **Playbook**: id, name, description, repo_path, stored_content, default_vars, owner_id
- **PlaybookTarget**: связывает playbook с host/group + snapshot
- **JobRun**: id, playbook_id, triggered_by, status, logs, started_at, finished_at, target_snapshot
- **Secret**: id, name, type, encrypted_value, metadata, scope, tags, created_by
- **CredentialReference**: связь Host->Secret (credential)
- **AutomationSchedule**: playbook_id, cron, enabled

## API (черновой)
- `POST /auth/login` — получить JWT
- `GET /auth/me`
- `GET /hosts` — фильтры, search
- `POST /hosts`
- `GET /hosts/{id}`
- `PUT /hosts/{id}`
- `DELETE /hosts/{id}`
- `POST /hosts/{id}/status-check`
- `WebSocket /hosts/{id}/terminal` — ssh tunnel (пароль или приватный ключ)
- `GET /groups`, `POST /groups`, `PUT /groups/{id}`, `DELETE /groups/{id}`, `POST /groups/{id}/recalculate`
- `GET /playbooks`, `POST /playbooks`, `GET /playbooks/{id}`, `PUT /playbooks/{id}`, `DELETE /playbooks/{id}`
- `POST /playbooks/{id}/run` — ручной запуск
- `GET /runs`, `GET /runs/{id}`
- `POST /runs/{id}/logs` (streaming/ws)
- `GET /secrets`, `POST /secrets`, `PUT /secrets/{id}`, `DELETE /secrets/{id}`, `POST /secrets/{id}/reveal`
- `GET /health`, `GET /metrics`

## Структура каталогов
```
/apps/backend        # FastAPI + SQLAlchemy + auth + api
/apps/frontend       # React + Vite + xterm.js
/apps/worker         # Scheduler (polling) + ansible executor + dynamic groups recompute
/deploy              # docker-compose.yml
/docs                # архитектура, roadmap, чек-листы, ADR
/scripts             # bootstrap, lint, test helpers
/.env.example       # окружение
```

## Воркер (детали)
- **Очередь запусков**: Redis list `itmgr:runs:queue` (BLPOP).
- **Таймауты/ретраи**:
  - `WORKER_RUN_TIMEOUT_SECONDS` — общий таймаут выполнения `ansible-playbook` (по умолчанию `1800`).
  - `WORKER_RUN_MAX_RETRIES` — лимит повторов при временных сбоях (по умолчанию `3`).
  - `WORKER_RUN_STALE_SECONDS` — watchdog для зависших `running` запусков (по умолчанию `3600`).
- **Артефакты запусков (безопасность)**:
  - В `/var/ansible/runs/{run_id}` сохраняются только безопасные файлы: `run.log`, `playbook.yml`, `inventory.public.ini`.
  - Файлы, которые могут содержать секреты (`inventory.ini`, `extra_vars.json`, `key_*.pem`) удаляются после завершения запуска (по умолчанию).
  - Для отладки можно включить сохранение чувствительных файлов: `WORKER_KEEP_SENSITIVE_ARTIFACTS=true` (не рекомендуется в проде).
- **Безопасность секретов**: воркер раскрывает секреты только через internal endpoint (admin-token), значения не логируются.

## Observability (MVP)
- **`X-Request-Id`**: backend проставляет `X-Request-Id` в каждом ответе; клиент/воркер может передать свой `X-Request-Id` для корреляции.
- **Логирование**:
  - по умолчанию — человекочитаемый формат с `request_id=...`;
  - `JSON_LOGS=1` включает JSON-логи (удобно для ELK/Loki).
- **Практика в воркере**: воркер прокидывает `X-Request-Id` с префиксами вроде `worker-run-<id>-...`, `worker-schedule-...` для удобного поиска по конкретному запуску/расписанию.

## Следующие документы
- `docs/ROADMAP.md` — фазы и чек-листы
- `docs/CHECKLISTS.md` — шаблоны задач/статуса
- `docs/API.md` — краткое описание API v1
```

## Healthchecks (Docker Compose)
- Backend: `GET /healthz`
- В `deploy/docker-compose.yml` настроены healthchecks для `db`, `redis`, `backend`, `frontend`, `worker`.

## SSH demo (для разработки/тестов)
- В `deploy/docker-compose.yml` добавлен `ssh-demo` — встроенный SSH-хост (доступен только внутри docker network).
- Учетные данные: `demo / demo123`.
- Используется в e2e тестах терминала (Playwright) и удобен для ручной проверки SSH/Ansible без внешней инфраструктуры.
