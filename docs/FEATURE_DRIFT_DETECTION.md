# Feature: Drift Detection + Auto‑Remediation

## Цель
Обнаруживать отклонения состояния хостов от desired state и автоматически запускать remediation.

## Источники данных
- Ansible facts (OS, packages, services)
- Host tags и inventory metadata
- Playbook outputs (optional)

## Модель
Новые сущности:
- `DriftPolicy` (project_id, name, enabled, rule_json, remediation_playbook_id, severity)
- `DriftEvent` (project_id, host_id, policy_id, status, detected_at, resolved_at, details)

## Rule engine (MVP)
- JSON‑правила: поля facts/tags, сравнения (equals, contains, version_lt, regex)
- Оценка по расписанию (каждые N минут) в воркере

## API (draft)
- `GET/POST/PUT/DELETE /api/v1/drift-policies`
- `GET /api/v1/drift-events` (filters: host_id, policy_id, status)

## Auto‑remediation
- При `policy.auto_remediate=true` → запуск playbook с host_id
- Требуется approval для prod

## UI
- Раздел “Drift”: список событий + политики
- Карточка события: правило, host, remediation run

## Audit
- drift.detected, drift.remediated, drift.resolved

## Риски
- Ложные срабатывания без качественных правил
- Нагрузка на воркер при частых checks
