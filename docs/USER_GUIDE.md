# IT Manager — Пользовательская документация

## Введение
IT Manager — веб‑панель для инвентаризации, доступа и автоматизации IT‑инфраструктуры. Документ описывает работу по разделам интерфейса, ключевые поля форм, логику и примеры.

### Роли и доступы
- admin — полный доступ, включая reveal секретов, пользователей, audit и admin settings.
- operator — управление хостами/группами, запуск автоматизации.
- viewer — только просмотр.
- automation-only — доступ к Automation без Hosts/Secrets.

### Вход
1) Откройте `Settings`.
2) Введите email/пароль.
3) Убедитесь, что выбран нужный проект в topbar.

---

## Проекты (Projects / Tenants) {#projects}
Проект изолирует сущности: hosts, groups, secrets, playbooks, runs. Все запросы UI отправляются с `X-Project-Id`.

- Переключатель проекта находится в topbar.
- После смены проекта данные перезагружаются.
- Если доступ к проекту ограничен — обратитесь к admin.

---

## Dashboard {#dashboard}
Показывает обзор:
- статус хостов (online/offline/unknown);
- последние запуски автоматизации;
- секреты с ближайшим сроком истечения;
- последние SSH‑сессии (admin).

Кнопка `Обновить` выполняет повторную загрузку данных.

---

## Hosts (Инвентаризация) {#hosts}

### Список
Фильтры и поиск:
- Поиск по `name` и `hostname`.
- Фильтры: `status`, `environment`, `os`, `tags`.
- Клик по строке открывает редактирование.
- Пагинация по странице; можно выбрать размер страницы.
- Пакетные действия: удалить выбранные хосты (admin/operator).

### Поля формы
- `name` — имя хоста в панели.
- `hostname` — DNS имя или IP.
- `port` — порт SSH (по умолчанию 22).
- `username` — логин для SSH.
- `os_type` — linux/windows и т.п.
- `environment` — prod/stage/dev (используется в RBAC и approvals).
- `tags` — JSON ключ‑значение для группировки и триггеров.
- `credential` — ссылка на секрет (password/private_key).
- `check_method` — tcp/ping/ssh (проверка статуса).
- `record_ssh` — запись SSH‑сессий.

### Действия
- `Проверить` — status‑check (tcp/ping/ssh).
- `Детали` — карточка хоста.
- `Терминал` — SSH терминал в браузере.
- `Удалить` — удаляет хост и его связь с группами.

**Пример tags**:
```json
{"role":"db","env":"prod"}
```

---

## Groups {#groups}
Группы бывают статические и динамические.

Дополнительно:
- Поиск по имени/описанию/типу.
- Пагинация и выбор размера страницы.
- Пакетное удаление выбранных групп (admin/operator).

### Static group
Выбираются конкретные хосты.

### Dynamic group
Используется правило в JSON:
- `environments` — список сред.
- `tags` — ключ‑значение, должны совпасть.

**Пример**:
```json
{"environments":["prod"],"tags":{"role":"db"}}
```

---

## Secrets {#secrets}
Типы: `text`, `password`, `token`, `private_key`.

Дополнительно:
- Поиск и фильтры по типу/scope.
- Пагинация и выбор размера страницы.
- Пакетное удаление выбранных секретов (admin).

### Поля формы
- `name` — имя секрета.
- `type` — тип секрета.
- `scope` — `project` (по умолчанию) или `global`.
- `description` — описание.
- `tags` — JSON ключ‑значение.
- `expires_at` — дата истечения.
- `rotation_interval_days` — период ротации.
- `value` — значение секрета.
- `passphrase` — пароль для private_key.
- `dynamic_enabled` — включить leases.
- `dynamic_ttl_seconds` — TTL lease.

### Reveal
Раскрытие значения доступно только admin.

---

## Будущие возможности {#future}
Ключевые функции, которые планируются для следующих релизов (см. `docs/ROADMAP.md`):
- JIT‑доступы с approvals и TTL
- Drift detection + auto‑remediation
- Change windows для prod‑запусков
- Compliance/Policy‑as‑Code

### Rotation
- Ручная ротация — ввод нового значения.
- Плановая ротация — по `rotation_interval_days`.
- Для `password` можно применить ротацию на хостах.

### Dynamic secrets (leases)
- Включите `dynamic_enabled` и задайте `dynamic_ttl_seconds`.
- Кнопка `Lease` выдает временное значение.

---

## Automation {#automation}

### Playbooks {#automation-playbooks}
- `stored_content` — YAML плейбук, хранится в БД.
- Git‑источник: `repo_url`, `repo_ref`, `repo_playbook_path`.
- `repo_auto_sync` — авто‑sync перед запуском.

### Templates / Instances {#automation-templates}
- Template: `vars_schema` и `vars_defaults`.
- Instance: `values` + targets (hosts/groups).

**Пример vars_schema**:
```json
{
  "app_version": {"type": "string"},
  "environment": {"type": "enum", "enum": ["prod", "stage", "dev"]},
  "db_password": {"type": "secret", "use_only": true}
}
```

**Пример vars_defaults**:
```json
{"environment":"stage"}
```

### Triggers {#automation-triggers}
Автозапуск по событиям:
- `host_created`
- `host_tags_changed`
- `secret_rotated`

Фильтры:
- поиск по id/типу/плейбуку;
- фильтр по типу события.
- пагинация и page size;
- пакетные действия: enable/disable/delete (admin).

### Runs / Approvals {#automation-runs}
- История запусков и статусы.
- Live‑лог (SSE).
- Для prod запусков возможен approval (admin).
- Фильтры: статус + поиск по id/плейбуку/commit/actor.
- Approvals: опция “только pending”.
- Пагинация: выбор размера страницы и навигация.
- Batch approvals: approve/reject выбранных (admin).

### Schedule (MVP)
- `enabled` — включить расписание.
- `type` — interval или cron.
- `value` — секунды (interval) или cron выражение.
- `host_ids` / `group_ids` — цели запуска.
- `extra_vars` — JSON параметры.

**Пример extra_vars**:
```json
{"app_version":"1.2.3","feature_flag":true}
```

**Пример cron**:
```
0 */6 * * *
```

---

## SSH Terminal {#ssh}
Доступен на карточке хоста.
- Поддержка password/private_key.
- При включенной записи — сохраняется transcript.

---

## Settings {#settings}
Раздел содержит доступ к сессии, проектам, пользователям, audit log, уведомлениям, плагинам и глобальным настройкам.

### Сессия {#settings-session}
- вход/выход и режим таблиц.

### Проекты {#settings-projects}
- список проектов и создание.

### Пользователи {#settings-users}
- создание пользователей, роли и ограничения (admin).
- ограничения: environments, group_ids, project_ids.

### Audit log {#settings-audit}
- просмотр событий CRUD/SSH/Automation и экспорт (admin).

### Notifications {#settings-notifications}
- webhooks/каналы и события (admin).
- можно выбрать конкретные события или отправлять все.

### Plugins {#settings-plugins}
- plugin instances, default и enable/disable (admin).
- `definition` определяет тип backend.

### Admin settings {#settings-admin}
- maintenance/banner/default project (admin).

---

## Notifications {#notifications}
Поддерживаются webhooks и каналы:
- webhook
- slack
- telegram
- email

Можно выбрать события: `run.failed`, `approval.requested`, `secret.expiring` и др.

**Пример payload события**:
```json
{
  "event": "run.failed",
  "project_id": 1,
  "payload": {
    "run_id": 42,
    "playbook_id": 5,
    "status": "failed",
    "triggered_by": "manual",
    "started_at": "2025-01-01T10:00:00Z"
  }
}
```

**Пример заголовка для webhook secret**:
```
X-Webhook-Secret: <secret>
```

---

## Plugins {#plugins}
Плагины — подключаемые backend‑ы для inventory/secrets/automation.

Вкладка `Plugins` (admin):
- создание instance;
- выбор default plugin для типа;
- включение/отключение.

---

## Audit Log {#audit}
Admin‑раздел для просмотра событий CRUD/SSH/Automation с фильтрами и экспортом.

---

## Troubleshooting {#troubleshooting}

### Не вижу данные проекта
- Проверьте выбранный проект в topbar.
- Убедитесь, что у пользователя есть доступ к проекту.

### Терминал не подключается
- Убедитесь, что `credential` задан (password/private_key).
- Проверьте `hostname` и `port`.
- Если статус offline — выполните `Проверить`.

### Status-check не работает
- `ping` требует `iputils-ping` в backend контейнере.
- Для `ssh` требуется credential.

### Sync playbook из Git не выполняется
- Проверьте `repo_url`, `repo_ref`, `repo_playbook_path`.
- Убедитесь, что у воркера есть доступ к репозиторию.

### Approval не появляется
- Для approval нужны цели с environment=prod.
- Проверьте вкладку `Runs/Approvals`.

---

## Примеры конфигураций {#examples}

### SSH credential (password)
```json
{"secret_type":"password","value":"SuperSecret123"}
```

### SSH credential (private_key)
```json
{"secret_type":"private_key","value":"-----BEGIN OPENSSH PRIVATE KEY-----\\n...","passphrase":"optional"}
```

### Пример playbook trigger (filters)
```json
{"environments":["prod"],"tags":{"role":"web"}}
```

### Пример inventory tag filter
```json
{"tags":{"env":"prod","role":"db"}}
```

---

## Doxygen (документация коду) {#doxygen}
Сборка Doxygen включена в `docker compose` и запускается при старте проекта.

Команды:
- Запуск всего стека: `docker compose -f deploy/docker-compose.yml up -d`
- Ручной запуск Doxygen: `docker compose -f deploy/docker-compose.yml run --rm doxygen`

Где смотреть результат:
- `docs/doxygen/html/index.html`

Примечание: генерация выполняется в отдельном контейнере `doxygen` и не влияет на runtime сервисов.
