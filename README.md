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
- Группы хостов: static/dynamic, rule engine, пересчёт состава (воркером и вручную).
- Vault-секреты (AES-GCM) с `/api/v1/secrets` и `/api/v1/secrets/{id}/reveal`, включая тип `private_key` с passphrase.
- Automation (MVP): CRUD плейбуков (stored_content), запуск, очередь Redis, воркер-исполнитель `ansible-playbook`, история и live-логи (SSE).
- Надёжность Automation: таймауты выполнения, ограниченные ретраи на временные сбои, watchdog зависших запусков (running слишком долго).
- Расписания Automation (MVP): interval/cron, выполняются воркером (см. ADR 0002).
- Audit log (MVP): события CRUD/SSH/Automation с просмотром в Settings (admin-only).
- React/Vite шаблон admin layout и Docker Compose окружение.
- React/Vite страницы Dashboard + Hosts (таблица, карточка, форма).
- React/Vite страницы Groups + Secrets + Settings (login/logout, reveal для admin, audit log).
- Страница Terminal с WebSocket-подключением и xterm.js; backend терминал использует SSH с паролем или приватным ключом + passphrase (через Secret).
- Миграции Alembic: backend применяет `alembic upgrade head` при старте контейнера.
- Healthcheck: `GET /healthz`.

## Projects / Tenants (как работает)

- Для HTTP API текущий проект задаётся заголовком `X-Project-Id`.
- Если `X-Project-Id` не передан: используется `default` (если доступен пользователю) или первый доступный проект из `users.allowed_project_ids`.
- Для WS/SSE endpoints проект передаётся query param `project_id` (UI делает это автоматически).
- Secrets:
  - `scope=project` — секрет привязан к текущему проекту.
  - `scope=global` — секрет общий для всех проектов (project_id = NULL); виден в списке Secrets любого проекта, но создаётся/редактируется/раскрывается только admin.

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

- расширить auth (пользователи в БД, полноценный RBAC).
- внедрить Alembic autogenerate и последующие миграции (после MVP idempotent init).
- улучшить Automation: артефакты, ansible-runner, UI полировки.
- покрыть критичные модули тестами и логами.

> Вся платформа готова к запуску `docker compose -f deploy/docker-compose.yml up -d`.
