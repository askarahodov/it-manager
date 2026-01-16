# Feature: JIT‑доступ (SSH/Secrets)

## Цель
Снизить риск постоянных доступов и обеспечить контролируемую выдачу доступа по запросу с TTL и approvals.

## Пользовательский сценарий
1) Пользователь создаёт запрос на доступ к хосту/секрету.
2) Система создаёт approval (если требуется политикой).
3) После подтверждения доступ активируется на ограниченное время (TTL).
4) По истечении TTL доступ автоматически отзывается.
5) Все действия фиксируются в audit log.

## Область применения
- SSH доступ к хостам
- Reveal/use секретов (password/private_key/token)

## Политики
- Требовать approval для env=prod и/или секретов с меткой `sensitivity=high`.
- Ограничивать по ролям (operator/viewer не может инициировать без политики).
- TTL по умолчанию: 30–120 минут (настраивается).

## Модель данных
Новая сущность: `AccessGrant`
- id
- project_id
- subject_user_id
- subject_email
- resource_type: host|secret
- resource_id
- scope: ssh|reveal|use
- status: pending|active|expired|revoked|rejected
- requested_at, approved_at, expires_at, revoked_at
- reason, approver_id
- policy_snapshot (JSON)

## API (draft)
- `POST /api/v1/access-requests` — создать запрос
- `GET /api/v1/access-requests` — список (фильтры по статусу/проекту)
- `POST /api/v1/access-requests/{id}/approve`
- `POST /api/v1/access-requests/{id}/reject`
- `POST /api/v1/access-requests/{id}/revoke`

## Enforcement
- SSH terminal допускается только если есть активный grant со scope=ssh.
- Reveal secrets — только если активен grant со scope=reveal.
- Use‑only secrets — активный grant со scope=use.

## UI
- Раздел: Access Requests (таблица, статусы, TTL).
- В Host/Secret карточке кнопка “Запросить доступ”.
- Для admin: подтверждение/отклонение, комментарий.

## Audit
- audit events: access.request, access.approve, access.reject, access.revoke, access.expire.

## Риски
- Сложность UX — нужна ясная коммуникация статусов и TTL.
- Гонка запросов (несколько approvals) — запретить дубликаты для одной пары (user, resource, scope).
