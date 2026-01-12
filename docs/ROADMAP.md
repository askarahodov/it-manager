# Roadmap IT Manager

## Фаза 1: Bootstrap + Auth + UI shell
- [x] определить стек и архитектуру
- [x] подготовить базовые docker-compose сервисы
- [x] реализовать auth + JWT + RBAC (users в БД + bootstrap admin)
- [x] создать layout админки и фиктивный платеж

## Фаза 2: Hosts CRUD + статус
- [x] модель Host и CRUD API
- [x] таблица хостов на фронте
- [x] поиск/фильтры/сортировка (MVP)
- [x] endpoint проверки статуса
- [x] визуализация статуса и логирование (базовая)

## Фаза 3: SSH terminal
- [x] WebSocket-прокси SSH (пароль/ключ) для терминала
- [x] tab Terminal на клиенте + xterm.js
- [x] логирование подключений

## Фаза 4: Groups static/dynamic
- [x] модель Group, правила и пересчёт
- [x] UI для управления группами
- [x] обновление состава (периодически воркером + ручной пересчёт)

## Фаза 5: Secrets vault + интеграции
- [x] CRUD для секретов с шифрованием
- [x] UI без отображения значений
- [x] интеграция секретов с Host и Playbook vars

## Фаза 6: Ansible playbooks + runs + history + schedules
- [x] модель Playbook/JobRun + API (MVP)
- [x] запуск через worker + ansible-playbook (Redis очередь)
- [x] история запусков + логи + live-лог (SSE)
- [x] артефакты запусков (run.log/playbook/inventory.public) + скачивание (admin-only)
- [x] scheduler/cron (MVP)
- [x] retries/таймауты + watchdog (hardening)

## Фаза 7: Hardening
- [x] RBAC и audit-логи (MVP)
- [x] users в БД + bootstrap admin + Users CRUD (admin-only)
- [x] unit тесты (базовые)
- [x] integration тесты
- [x] docs/ADR + README + healthchecks
- [x] observability (X-Request-Id, JSON_LOGS)
- [x] toasts и подтверждения (UX)
- [x] UI polishing (прочее)

## Фаза 8: RBAC 2.0 + ограничения (Enterprise-ready)
- [x] расширить роли: admin/operator/viewer/automation-only (+ legacy user)
- [x] матрица прав (hosts/secrets/ansible) + enforcement в API (hosts/groups/secrets/playbooks/runs/terminal)
- [x] ограничения по groups/environment (prod/stage/dev): поля в users + фильтрация hosts/groups на backend
- [x] Secrets: режим use-only — secrets используются в runtime (SSH/Ansible), но reveal доступен только admin
- [x] UI: управление ограничениями env/groups и ролями (минимальный UX без усложнений)

## Фаза 9: Projects / Tenants + переключатель проекта
- [x] сущность Project (tenant) + привязка hosts/groups/secrets/playbooks/runs
- [x] ограничения доступа пользователей по проектам (allowed_project_ids)
- [x] единый fallback выбора проекта (default/allowlist) для HTTP и WS terminal
- [x] глобальные сущности (shared secrets) и политика доступа
- [x] UI: Project switcher в topbar (как GitLab) + изоляция данных
- [x] миграция существующих данных в default project

## Фаза 10: Advanced Host Health (лайтовый мониторинг)
- [ ] расширенный health snapshot: uptime/load/disk/memory
- [ ] last ansible run status на карточке хоста
- [ ] history (упрощённый time-series) + хранение последнего статуса
- [ ] custom checks через ansible facts/модули (MVP)

## Фаза 11: Automation 2.0
- [x] playbook templates (vars schema + defaults)
- [x] instances (values + binding hosts/groups)
- [x] auto-generated форма с валидацией типов (string/enum/secret/use-only)
- [x] approval flow для prod (requester/approver + история)
- [x] approval diff параметров (before/after по запуску)
- [x] event-driven triggers: webhook/api call
- [x] event-driven triggers: host added/tag changed
- [ ] event-driven triggers: secret rotated

## Фаза 12: Secrets Vault — Enterprise
- [ ] secret rotation (manual/scheduled) + политики
- [ ] уведомления: expiring soon / rotated
- [ ] интеграция rotation с SSH passwords/API tokens (MVP)
- [ ] dynamic secrets (опционально): TTL creds + auto revoke

## Фаза 13: SSH & Remote Operations
- [ ] SSH session recording (metadata): duration/user/host/success-error
- [ ] full session recording (опционально): флаг + предупреждение + хранение
- [ ] remote actions (reboot/restart service/fetch logs/upload file) через ansible ad-hoc

## Фаза 14: UI/UX как у зрелого продукта
- [ ] global search + Cmd/Ctrl+K quick actions
- [ ] dashboard widgets: hosts status/failed runs/upcoming schedules/expiring secrets/recent SSH
- [ ] audit log UI: фильтры + экспорт + before/after + source/IP

## Фаза 15: Интеграции и масштабирование
- [ ] git integration: playbooks из repo + auto-sync + commit hash в run history
- [ ] notifications: Slack/Telegram/Email (failed run/approval needed/secret expiring/host offline)
- [ ] webhooks: inbound triggers + outbound notifications
- [ ] plugin system (inventory/secrets/automation backends)
- [ ] HA/scale: multiple workers, distributed locks, sharding
