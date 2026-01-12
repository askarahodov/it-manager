# IT Manager

IT Manager объединяет инвентаризацию хостов, SSH-доступ, secure vault и автоматизацию Ansible в одном admin dashboard. Пилотная версия состоит из FastAPI backend, React/Vite frontend и worker-контейнера для выполнения задач.

## Быстрый старт

1. Скопируйте `.env.example` в `.env` и задайте `MASTER_KEY`/`SECRET_KEY`.
2. Запустите `docker compose -f deploy/docker-compose.yml up --build`.
   - Compose автоматически подхватывает переменные из `.env` в корне репозитория.
3. Backend доступен по `http://localhost:8000`, Swagger — `http://localhost:8000/docs`.
4. Фронтенд работает на `http://localhost:4173`.
   - Запросы `/api/*` проксируются фронтендом в backend (nginx).
5. Для тестов и демонстрации в compose поднят `ssh-demo` (только внутри docker network): `demo / demo123`.
5. При первом старте создаётся bootstrap admin (если таблица `users` пуста): `BOOTSTRAP_ADMIN_EMAIL`/`BOOTSTRAP_ADMIN_PASSWORD`.
6. Healthchecks: `GET http://localhost:8000/healthz` и `docker compose -f deploy/docker-compose.yml ps`.
7. Observability (опционально): `JSON_LOGS=1` включает JSON-логи; каждый ответ backend содержит заголовок `X-Request-Id` (можно прокидывать свой).

## Восстановление репозитория (если «всё пропало» после `git pull`)

Если вы случайно подтянули пустую ветку и рабочее дерево стало пустым, часто помогает `git stash` (туда могли попасть untracked файлы).

Проверьте и восстановите:

```bash
git stash list
git stash show --name-only --include-untracked stash@{0} | head
git stash apply --index stash@{N}
```

После восстановления обязательно зафиксируйте работу в git, иначе повторная ошибка снова «сотрёт» файлы:

```bash
git add -A
git commit -m "restore: project files"
```

## E2E (Playwright)

E2E тесты живут в `apps/frontend/tests-e2e` и поднимают весь stack через `deploy/docker-compose.yml`.

### Установка браузера

Выполняется один раз (может занять время):

`cd apps/frontend && npx playwright install chromium chromium-headless-shell`

По умолчанию Playwright использует системный кеш браузеров.
Если нужно хранить браузеры в репозитории: `E2E_BROWSERS_IN_REPO=1`.

### Прогон тестов (рекомендуется)

Полный автономный прогон (поднимет compose, дождётся readiness, соберёт report):

`bash scripts/test-e2e.sh`

Быстрый прогон по уже поднятому stack:

`cd apps/frontend && E2E_REUSE_SERVER=1 npx playwright test`

### Артефакты

- HTML отчёт: `apps/frontend/playwright-report/`
- Артефакты Playwright (trace/video/скриншоты фейлов): `apps/frontend/test-results/`
- Скриншоты “smoke” (до/после): `apps/frontend/e2e-artifacts/screenshots/latest/` и `apps/frontend/e2e-artifacts/screenshots/<run-id>/`

Переменные для максимальной “видимости” (trace/video/screenshot всегда):

`E2E_TRACE=on E2E_VIDEO=on E2E_SCREENSHOT=on`

## Что уже реализовано

- FastAPI backend с router-структурой, конфигами и CORS.
- JWT auth (users в БД): `POST /api/v1/auth/login` выдаёт токен.
- Endpoint `GET /api/v1/auth/me` возвращает текущую роль/пользователя (для UI).
- Projects/Tenants: изоляция доменных сущностей по проекту (`project_id`) + UI переключатель проекта.
- CRUD хостов + статус-чек `POST /api/v1/hosts/{id}/status-check`.
- Hosts: метод проверки статуса на хосте `check_method`: `ping`/`tcp`/`ssh` (по умолчанию `tcp`).
- Advanced host health: snapshot (uptime/load/memory/disk) + history + facts через Ansible.
- Группы хостов: static/dynamic, rule engine, пересчёт состава (воркером и вручную).
- Vault-секреты (AES-GCM) с `/api/v1/secrets` и `/api/v1/secrets/{id}/reveal`, включая тип `private_key` с passphrase, scope `global`, `expires_at`, rotation interval и ручную ротацию (`/api/v1/secrets/{id}/rotate`).
- Ротация SSH password с применением на хостах через системный playbook (`/api/v1/secrets/{id}/rotate-apply`).
- Плановая ротация секретов (password/token) выполняется воркером по интервалу (`WORKER_ROTATION_POLL_SECONDS`).
- Automation: CRUD плейбуков, playbook templates/instances, запуск вручную/по расписанию, история и live-логи (SSE).
- Git integration: playbooks из repo + ручной sync и auto-sync на запуске, commit hash сохраняется в run history.
- Approval flow для prod запусков: requester/approver, diff параметров, UI approvals.
- Event-driven triggers: webhook, host created/tags changed, secret rotated.
- Надёжность Automation: таймауты выполнения, ограниченные ретраи на временные сбои, watchdog зависших запусков (running слишком долго).
- Расписания Automation (MVP): interval/cron, выполняются воркером (см. ADR 0002).
- Audit log: события CRUD/SSH/Automation с фильтрами, экспортом и source IP (admin-only).
- Notifications (webhook/slack/telegram/email): события run/approval/host/secret на внешний URL.
- React/Vite шаблон admin layout и Docker Compose окружение.
- React/Vite страницы Dashboard + Hosts (таблица, карточка, форма).
- React/Vite страницы Groups + Secrets + Settings (login/logout, reveal для admin, audit log).
- Страница Terminal с WebSocket-подключением и xterm.js; backend терминал использует SSH с паролем или приватным ключом + passphrase (через Secret).
- SSH session recording (metadata): длительность, актор, IP, статус.
- SSH full recording (опционально): флаг записи + хранение transcript.
- Remote actions: reboot/restart service/fetch logs/upload file через Ansible.
- Миграции Alembic: backend применяет `alembic upgrade head` при старте контейнера.
- Healthcheck: `GET /healthz`.
- UI: dashboard widgets, approval diff, compact tables, global search (Cmd/Ctrl+K).

## Projects / Tenants (как работает)

- Для HTTP API текущий проект задаётся заголовком `X-Project-Id`.
- Если `X-Project-Id` не передан: используется `default` (если доступен пользователю) или первый доступный проект из `users.allowed_project_ids`.
- Для WS/SSE endpoints проект передаётся query param `project_id` (UI делает это автоматически).
- Secrets:
  - `scope=project` — секрет привязан к текущему проекту.
  - `scope=global` — секрет общий для всех проектов (project_id = NULL); виден в списке Secrets любого проекта, но создаётся/редактируется/раскрывается только admin.

## Automation: approvals, triggers, webhooks (коротко)

- Approval для prod: если среди целей есть хосты `environment=prod`, запуск создаётся в статусе pending и требует подтверждения admin.
- Triggers:
  - `host_created`, `host_tags_changed` — автозапуск по событиям хоста.
  - `secret_rotated` — автозапуск при обновлении значения секрета (если секрет используется как credential у хостов).
- Webhook: плейбук можно запускать по HTTP с токеном.

### Webhook запуск плейбука

1) Сгенерируйте токен (admin):

`POST /api/v1/playbooks/{id}/webhook-token`

2) Запуск:

`POST /api/v1/playbooks/{id}/webhook?token=...`

Body:

```json
{"host_ids":[1],"group_ids":[],"extra_vars":{"key":"value"},"dry_run":true}
```

## Тесты (backend)

Unit-тесты (в контейнере backend): `docker compose -f deploy/docker-compose.yml exec -T -w /app backend pytest -q`

Integration-тесты: `docker compose -f deploy/docker-compose.yml exec -T -w /app backend env PYTHONPATH=/app pytest -c pytest_integration.ini -q`

## Структура

- `/apps/backend` — FastAPI, SQLAlchemy, encrypt/routers.
- `/apps/frontend` — Vite + React shell.
- `/apps/worker` — воркер для scheduler/ansible.
- `/deploy/docker-compose.yml` — Compose stack.
- `/docs` — архитектура, roadmap, чек-листы, ADR.
- `/scripts` — bootstrap/lint/test.

## Что дальше

- git integration для playbooks + auto-sync.
- dynamic secrets (TTL creds + auto revoke).
- plugin system (inventory/secrets/automation backends).
- HA/scale: multiple workers + distributed locks + sharding.

> Вся платформа готова к запуску `docker compose -f deploy/docker-compose.yml up -d`.

## Git playbooks (как пользоваться)

1) В Automation создайте/откройте плейбук и заполните:
   - `Repo URL` (git URL),
   - `Ref` (branch/tag/commit, опционально),
   - `Playbook path` (путь до playbook.yml в репозитории).
2) Нажмите `Sync now` (или включите auto-sync перед запуском).
3) При каждом запуске commit сохраняется в history.

Переменные окружения:
- `REPO_SYNC_DIR` — каталог для checkout репозиториев (по умолчанию `/app/data/repos`).
