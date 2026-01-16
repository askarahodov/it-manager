# Backlog IT Manager

Формат: P0/P1/P2, статус (planned/in_progress/done), владелец, зависимость, критерии приёмки.

## P0 — безопасность
- [ ] JIT‑доступ к SSH/Secrets (in_progress)
  - Описание: выдача временных доступов по approval, TTL, auto‑revoke.
  - Критерии: журнал действий, ревокация по TTL, запрет reveal вне approval.
- [ ] SSO (OIDC) + MFA (planned)
  - Критерии: вход через OIDC, enforced MFA, fallback локальные admin.
- [ ] Audit log WORM + экспорт в SIEM (planned)
  - Критерии: неизменяемое хранение, экспорт, фильтрация по проекту.

## P1 — механизмы
- [ ] Drift detection + auto‑remediation (in_progress)
  - Критерии: правила сравнения состояния, события drift, автоматический run.
- [ ] Change windows (in_progress)
  - Критерии: блокировка запусков вне окна, override через approval.
- [ ] Compliance/Policy‑as‑Code (planned)
  - Критерии: правила на host tags/os/version, отчёт + алерты.

## P1 — масштабирование
- [ ] Multiple workers + distributed locks (in_progress)
  - Критерии: отсутствие дублей, масштабирование run‑очереди.
- [ ] Object storage for artifacts (planned)
  - Критерии: S3/minio, retention, ссылочный доступ.
- [ ] Read replicas / split reads (planned)
  - Критерии: readonly endpoints на репликах.

## P2 — интеграции
- [ ] CMDB Sync (NetBox/ServiceNow) (planned)
  - Критерии: импорт/экспорт hosts/groups, дедупликация.
- [ ] SDK/CLI (planned)
  - Критерии: базовые команды управления и запуска.
