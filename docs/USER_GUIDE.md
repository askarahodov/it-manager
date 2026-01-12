# IT Manager — Пользовательская документация

## Введение
IT Manager — это веб‑панель для инвентаризации хостов, управления доступом и автоматизации (Ansible). Документ описывает работу по разделам интерфейса.

### Роли
- admin — полный доступ, включая reveal секретов, настройки, пользователей, admin‑настройки.
- operator — управление хостами и группами, запуск автоматизации.
- viewer — просмотр.
- automation-only — доступ к автоматизации без доступа к инвентарю/секретам.

### Вход
1) Откройте раздел `Settings`.
2) Введите email/пароль.
3) Убедитесь, что в topbar выбран корректный проект.

---

## Проекты (Projects / Tenants)
Проект изолирует хосты/группы/секреты/плейбуки/запуски.

- Переключатель проекта находится в topbar.
- После смены проекта все списки перезагружаются.

---

## Дашборд
Раздел `Dashboard` показывает:
- статус хостов (online/offline/unknown);
- последние запуски автоматизации;
- секреты с ближайшими сроками истечения;
- последние SSH‑сессии (admin).

Подсказка: при недоступных данных используйте кнопку `Обновить`.

---

## Hosts (Инвентаризация)
### Список
- Поиск по имени/hostname.
- Фильтры по status, environment, os и тегам.
- Клик по строке открывает редактирование.

### Создание/редактирование
Поля:
- `name`, `hostname`, `port`, `username`, `os_type`, `environment`.
- `credential` — ссылка на секрет.
- `record_ssh` — включить запись SSH сессий.

### Действия
- `Проверить` — status-check.
- `Детали` — карточка хоста.
- `Терминал` — SSH терминал в браузере.

**Пример тегов**:
```json
{"role":"db","env":"prod"}
```

---

## Groups
Группы бывают статические и динамические.

### Static group
- Выбор конкретных хостов.

### Dynamic group
- Правило в JSON (rule), по среде/тегам.

**Пример динамического правила**:
```json
{"environments":["prod"],"tags":{"role":"db"}}
```

---

## Secrets
Типы: `text`, `password`, `token`, `private_key`.

### Создание
- Значение хранится зашифрованным.
- Reveal доступен только admin.

### Rotation
- Ручная ротация и/или интервал.
- Можно применить rotation к хостам (для password).

### Dynamic secrets (leases)
- Настройка TTL.
- Кнопка `Lease` выдаёт временное значение.

---

## Automation
### Playbooks
- Хранение YAML в `stored_content`.
- Опционально: Git‑репозиторий (URL/ref/path) + Sync.

### Templates / Instances
- Template содержит schema и defaults.
- Instance хранит конкретные values + цели (hosts/groups).

### Triggers
- Автозапуск по событиям: host_created, host_tags_changed, secret_rotated.

### Runs / Approvals
- История запусков с логами и статусом.
- Для prod запусков возможен approval (admin).

**Пример extra_vars**:
```json
{"app_version":"1.2.3","feature_flag":true}
```

---

## SSH Terminal
Доступен на карточке хоста.
- Поддержка password и private key.
- При включённой записи — сохраняется transcript.

---

## Settings
Раздел содержит:
- сессия и режим таблиц;
- управление пользователями и доступами (admin);
- проекты и переключение;
- audit log (admin);
- notifications (admin);
- plugins (admin);
- admin settings (maintenance/banner/default project).

---

## Notifications
Поддерживаются webhooks и каналы:
- webhook
- slack
- telegram
- email

Можно выбрать события: `run.failed`, `approval.requested`, `secret.expiring` и др.

---

## Plugins
Плагины — подключаемые backend‑ы для inventory/secrets/automation.

Вкладка `Plugins` (admin):
- создание instance;
- выбор default plugin для типа;
- включение/отключение.

---

## Audit Log
Admin‑раздел для просмотра событий CRUD/SSH/Automation с фильтрами и экспортом.

---

## Doxygen (документация коду)
Сборка Doxygen включена в `docker compose` и запускается при старте проекта.

Команды:
- Запуск всего стека: `docker compose -f deploy/docker-compose.yml up -d`
- Ручной запуск Doxygen: `docker compose -f deploy/docker-compose.yml run --rm doxygen`

Где смотреть результат:
- `docs/doxygen/html/index.html`

Примечание: генерация выполняется в отдельном контейнере `doxygen` и не влияет на runtime сервисов.
