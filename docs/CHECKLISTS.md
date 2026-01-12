# Списки задач IT Manager

## Общие
- [x] определить стек и создать архитектурное описание
- [x] настроить docker-compose и env шаблоны
- [x] подготовить базовые READMEs

## Backend
- [x] установить FastAPI + SQLAlchemy + Alembic
- [x] реализовать auth/roles
- [x] users в БД + bootstrap admin + Users CRUD (admin-only)
- [x] CRUD для Host/Secret (базовая реализация)
- [x] Hosts list: поиск/фильтры/сортировка (query params)
- [x] CRUD для Group (static/dynamic) + пересчёт
- [x] CRUD для Playbook (MVP: stored_content)
- [x] endpoint status-check + WS terminal (SSH, пароль/ключ)
- [x] worker: периодический пересчёт dynamic groups
- [x] очередь запусков (Redis) + JobRun API + live-лог (SSE)
- [x] артефакты запусков (run.log/playbook/inventory.public) + скачивание (admin-only)
- [x] scheduler + полноценный ansible-runner/расширенные артефакты

## Frontend
- [x] настроить Vite + TypeScript
- [x] создать основной layout (sidebar/topbar)
- [x] страницы: Dashboard, Hosts, Groups, Secrets, Settings
- [x] Hosts: поиск/фильтры/сортировка (MVP)
- [x] Hosts: фильтр по тегам + пагинация (MVP)
- [x] Host details: отдельная карточка + вкладка Terminal
- [x] страница: Automation (Playbooks + Runs + live logs)
- [x] интегрировать xterm.js для терминала
- [x] toast-уведомления и модалки подтверждения

## Инфраструктура
- [x] postgres + миграции (Alembic)
- [x] worker + ansible workspace volume
- [x] cron/scheduler (MVP: воркер polling)
- [x] healthchecks
- [x] observability и логирование (X-Request-Id, JSON_LOGS)

## Безопасность и документация
- [x] шифрование секретов (AES-GCM)
- [x] audit-логи CRUD/SSH/Automation (MVP)
- [x] docs/ADR + API docs
- [x] тесты критичных модулей (базовые unit)
- [x] интеграционные тесты (auth/hosts/secrets/groups/playbooks/runs)

## Планы (v0.2+): Enterprise / масштабирование

### RBAC 2.0
- [x] роли: admin/operator/viewer/automation-only (+ legacy user)
- [x] права: hosts (read/write/check/ssh), secrets (read_metadata/write/reveal/use), ansible (read/run/edit/schedule)
- [x] ограничения доступа по groups/environment (prod/stage/dev): поля users + фильтры на backend
- [x] Secrets use-only: использование в runtime без reveal (reveal только admin)
- [x] UI: редактирование ролей и ограничений (Settings)

### Projects / Tenants
- [x] Project entity + изоляция hosts/groups/secrets/playbooks/runs
- [x] ограничения доступа пользователей по проектам (allowed_project_ids) + enforcement в API/WS
- [x] единый выбор текущего проекта (fallback default/allowlist) для HTTP + WS terminal
- [ ] глобальные shared сущности (секреты/шаблоны) + политики доступа
- [x] UI: переключатель проекта в topbar
- [x] миграция текущих данных в default project
- [x] unit/integration тесты на project scoping и project fallback

### Advanced Host Health
- [ ] сбор метрик (uptime/load/disk/memory) + сохранение последнего статуса
- [ ] упрощённая история (time-series) для health checks
- [ ] last ansible run status на Host details
- [ ] custom checks через ansible facts (MVP)

### Automation 2.0
- [ ] playbook templates (vars schema + defaults)
- [ ] instances (values + binding)
- [ ] auto-generated форма + валидация типов (string/enum/secret/use-only)
- [ ] approval flow для prod (requester/approver + diff)
- [ ] event triggers: host added/tag changed/secret rotated/webhook/api call

### Secrets Enterprise
- [ ] rotation policies (manual/scheduled) + интеграции (SSH password / API token)
- [ ] уведомления: expiring soon / rotated
- [ ] dynamic secrets (опционально): TTL creds + auto revoke

### SSH & Remote Ops
- [ ] SSH session recording (metadata): duration/user/host/success/error
- [ ] optional full session recording (флаг + предупреждение)
- [ ] remote actions: reboot/restart/fetch logs/upload file (через ansible ad-hoc)

### UI/UX
- [ ] global search + Cmd/Ctrl+K quick actions
- [ ] dashboard widgets (status/runs/schedules/secrets/ssh activity)
- [ ] audit log UI: фильтры + экспорт + before/after + source/IP

### Интеграции и Ops
- [ ] git integration: auto-sync + commit hash в execution history
- [ ] notifications: Slack/Telegram/Email
- [ ] webhooks (inbound/outbound)
- [ ] plugin system (inventory/secrets/automation backends)
- [ ] scale/HA: multiple workers + distributed locks + sharding
