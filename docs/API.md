# API (v1) — IT Manager

Базовый URL (через frontend nginx proxy): `http://localhost:4173/api/v1/...`

Swagger/OpenAPI: `http://localhost:8000/docs`

## Аутентификация

Используется JWT (Bearer token).

- `POST /api/v1/auth/login`
  - body: `{ "email": "...", "password": "..." }`
  - response: `{ "access_token": "..." }`
- `GET /api/v1/auth/me`
  - header: `Authorization: Bearer <token>`
  - response: `{ "email": "...", "role": "admin|user" }`

## Ошибки и request-id

- Backend возвращает `X-Request-Id` в ответе (и принимает ваш `X-Request-Id`).
- Ошибки — JSON вида `{ "detail": "..." }` или `HTTP 4xx/5xx`.

## Projects / Tenants

Почти все доменные endpoints (hosts/groups/secrets/playbooks/runs/audit/terminal) работают в контексте текущего проекта.

- Выбор проекта для HTTP: заголовок `X-Project-Id: <id>`.
- Если `X-Project-Id` не передан: backend использует `default` (если доступен пользователю) или первый доступный проект из `users.allowed_project_ids`.
- Для WS/SSE endpoints проект передаётся query param `project_id` (рекомендуется всегда передавать, но есть fallback по тем же правилам).

Endpoints:

- `GET /api/v1/projects/` — список проектов (с учётом `users.allowed_project_ids`)
- `POST /api/v1/projects/` (admin) — создать проект
- `PUT /api/v1/projects/{id}` (admin) — обновить проект
- `DELETE /api/v1/projects/{id}` (admin) — удалить проект (кроме `default`)

## Hosts (Инвентаризация)

- `GET /api/v1/hosts/`
  - header: `X-Project-Id` (опционально)
  - query:
    - `search` — поиск по `name/hostname` (ILIKE)
    - `status` — `online|offline|unknown`
    - `environment`, `os_type`
    - `tag_key`, `tag_value`
    - `sort_by`: `name|hostname|status|environment|os_type|id`
    - `sort_dir`: `asc|desc`
    - `limit`, `offset`
- `POST /api/v1/hosts/` (admin)
  - поля:
    - `name`, `hostname`, `port`, `username`, `os_type`, `environment`, `tags`, `description`, `credential_id`
    - `check_method`: `ping|tcp|ssh` (по умолчанию `tcp`)
- `GET /api/v1/hosts/{id}`
- `PUT /api/v1/hosts/{id}` (admin)
- `DELETE /api/v1/hosts/{id}` (admin)
- `POST /api/v1/hosts/{id}/status-check`
  - выполняет проверку по `host.check_method` и сохраняет `status/last_checked_at`

### Терминал (SSH)

- `WebSocket /api/v1/hosts/{id}/terminal?token=<jwt>[&project_id=<id>]`
  - данные (text) проксируются в stdin SSH (PTY)
  - JSON команды:
    - `{"type":"resize","cols":123,"rows":45}`

## Secrets (Vault)

- `GET /api/v1/secrets/`
- `POST /api/v1/secrets/` (admin)
  - `type`: `text|password|token|private_key`
  - `value` — сохраняется в БД в зашифрованном виде (AES-GCM)
  - `passphrase` — опционально для `private_key`
- `PUT /api/v1/secrets/{id}` (admin)
  - если `value` пустой/не передан — значение не меняется
- `DELETE /api/v1/secrets/{id}` (admin)
  - если секрет привязан к Host — вернётся `HTTP 400`
- `POST /api/v1/secrets/{id}/reveal` (admin)
  - возвращает `{ "value": "..." }`
- `POST /api/v1/secrets/{id}/reveal-internal` (admin, internal-use)
  - используется воркером для подстановки секретов и сборки inventory

## Groups

- `GET /api/v1/groups/`
- `POST /api/v1/groups/` (admin)
- `PUT /api/v1/groups/{id}` (admin)
- `DELETE /api/v1/groups/{id}` (admin)
- `POST /api/v1/groups/recompute-dynamic` (admin) — пересчёт dynamic групп

## Automation (Playbooks/Runs)

- `GET /api/v1/playbooks/`
  - header: `X-Project-Id` (опционально)
- `POST /api/v1/playbooks/` (admin)
- `PUT /api/v1/playbooks/{id}` (admin)
- `DELETE /api/v1/playbooks/{id}` (admin)
- `POST /api/v1/playbooks/{id}/run`
  - body: `{ "host_ids": [...], "group_ids": [...], "extra_vars": {...}, "dry_run": false }`
  - `extra_vars` поддерживает ссылки на секреты: `{{ secret:ID }}`
- `GET /api/v1/runs/`
- `GET /api/v1/runs/{id}`
- `GET /api/v1/runs/{id}/stream?token=<jwt>[&project_id=<id>]` — SSE live-лог (EventSource без Authorization header)
- `GET /api/v1/runs/{id}/artifacts` (admin)
- `GET /api/v1/runs/{id}/artifacts/{name}?token=<jwt>[&project_id=<id>]` (admin)

## Users (RBAC)

admin-only:

- `GET /api/v1/users/`
- `POST /api/v1/users/`
- `PUT /api/v1/users/{id}` (смена роли/пароля)
- `DELETE /api/v1/users/{id}`

## Audit log

admin-only:

- `GET /api/v1/audit/?limit=100` (контекст проекта определяется через `X-Project-Id`)
