# Feature: Change Windows (Prod)

## Цель
Контролировать запуск automation в прод‑среде только в разрешённые окна времени.

## Модель
Новая сущность: `ChangeWindow`
- project_id, name, enabled
- schedule: cron/interval/time_range
- environments: [prod, stage]
- timezone
- override_policy: approval_required|admin_only

## Enforcement
- Запуски automation в prod блокируются вне окна.
- Возможен override через approval (если разрешено политикой).

## API (draft)
- `GET/POST/PUT/DELETE /api/v1/change-windows`

## UI
- Раздел Settings → Change Windows
- Отображение ближайшего окна на странице Automation

## Audit
- change_window.block, change_window.override

## Риски
- Временные зоны и переходы (DST)
