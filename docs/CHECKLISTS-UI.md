# UI чек-лист (Playwright + UX/UI полировка)

## Как запускать “зрение”

- `cd apps/frontend`
- Убедиться, что стек поднят: `docker compose -f deploy/docker-compose.yml up -d`
- Запуск E2E (с артефактами):
  - `E2E_REUSE_SERVER=1 E2E_TRACE=on E2E_VIDEO=on E2E_SCREENSHOT=on npm run test:e2e`
- Где смотреть:
  - Скриншоты: `apps/frontend/e2e-artifacts/screenshots/latest/`
  - Отчёт: `cd apps/frontend && npm run test:e2e:report`

## Найденные UX/UI проблемы (15+) по артефактам

### P0 (критично)

- [x] Secrets: бесконечная высота списка (полотно на тысячи пикселей), невозможно работать при большом количестве записей.
- [x] Sidebar: нет мобильного сценария (на узких экранах меню “съедает” контент, нет overlay/закрытия).
- [x] Tables: шапка теряется при прокрутке (нет sticky header), сложно ориентироваться в данных.
- [x] Groups (static): выбор хостов без поиска/фильтра — непригодно при большом инвентаре.
- [x] Риск горизонтального скролла на узких экранах (контент может “выползать” из viewport).

### P1 (важно)

- [x] Hosts: в фильтрах часть подписей на английском (“Tag key/value”, “Hostname”, “User”) — ломает консистентность локализации.
- [x] Sort UX: кликабельные заголовки таблиц без `aria-sort` и без явного affordance (кроме стрелок) — хуже A11y.
- [x] Automation: длинная форма без “быстрой навигации” и/или sticky action bar (сохранить/сброс) — много скролла.
- [x] Ошибки форм: нет единообразных inline ошибок под полями (местами только toast/общая ошибка).
- [x] Loading: нет skeleton/placeholder для таблиц (скачки layout при загрузке).

### P2 (можно улучшать дальше)

- [x] Контраст helper-текста на тёмной теме местами на грани читабельности.
- [ ] Единый стиль иконок/кнопок (например “Меню” как текст vs иконка) — косметика.
- [x] Табличные ячейки с длинными строками иногда слишком агрессивно переносятся (влияние на читабельность).
- [ ] Подсказки (title) не всегда заменяют явные подсказки в UI (особенно для touch).
- [x] Нет отдельного режима “компактно/просторно” для таблиц (полезно на больших экранах).

## Исправления (выполнено)

### 1) Secrets: ограничение высоты таблицы + sticky header (P0)

- [x] Обёртка таблицы в `div.table-scroll` + `max-height`/`overflow:auto`.
- [x] Sticky header в `.table-scroll .hosts-table thead th`.
- Скриншоты:
  - До: `apps/frontend/e2e-artifacts/screenshots/20251230-111103/03-secrets.png` (1280×5374)
  - После: `apps/frontend/e2e-artifacts/screenshots/20251230-113209/03-secrets.png` (1280×961)

### 2) Мобильное меню (P0)

- [x] Добавлен toggler “Меню” в topbar + overlay/backdrop для закрытия.
- Скриншоты:
  - До: `apps/frontend/e2e-artifacts/screenshots/20251230-111100/01-settings-authenticated.png`
  - После: `apps/frontend/e2e-artifacts/screenshots/20251230-113205/01-settings-authenticated.png`

### 3) Hosts: таблица в scroll-container (P1→P0 при большом списке)

- [x] Таблица хостов обёрнута в `div.table-scroll` (лучше контролируется высота, меньше “полотен”).
- Скриншоты:
  - До: `apps/frontend/e2e-artifacts/screenshots/20251230-111101/02-hosts.png`
  - После: `apps/frontend/e2e-artifacts/screenshots/20251230-113207/02-hosts.png`

### 4) Groups: удобство выбора хостов (P0)

- [x] Добавлен фильтр по имени/hostname перед multi-select.
- [x] Multi-select ограничен по высоте (прокрутка внутри).
- Скриншоты:
  - До: `apps/frontend/e2e-artifacts/screenshots/20251230-111105/04-groups.png`
  - После: `apps/frontend/e2e-artifacts/screenshots/20251230-113210/04-groups.png`

### 5) Адаптив и предотвращение горизонтального скролла (P0)

- [x] `body { overflow-x: hidden; }`
- [x] Адаптив для `.page-header` и `.status-summary` на узких экранах.

## Projects/Tenants: UI чек-лист

Цель: убедиться, что выбранный проект корректно изолирует данные и влияет на HTTP/WS/SSE запросы.

- [x] Project switcher: список проектов грузится после login и не ломает layout на mobile.
- [x] Выбор проекта сохраняется (после reload) и влияет на все страницы (Hosts/Groups/Secrets/Automation).
- [x] Все API запросы по умолчанию отправляют `X-Project-Id` (если проект выбран), но корректно работают и без него (fallback на доступный проект).
- [x] Terminal (WS): query param `project_id` соответствует выбранному проекту; при неверном/недоступном проекте — понятная ошибка в UI.
- [x] Runs live logs (SSE): query param `project_id` соответствует выбранному проекту; при смене проекта активные подписки корректно закрываются/переподключаются.
- [x] Смена проекта: нет “протечки” данных (после переключения не остаются сущности прошлого проекта в списках/карточках).
- [x] Ошибки 403/404 по проекту: показываются дружелюбно (toast + текст на странице), без бесконечных retries.

## Что дальше

- [x] Привести локализацию Hosts/filters к единому русскому словарю.
- [x] Добавить `aria-sort` и улучшить affordance сортировки в заголовках таблиц.
- [x] Сделать “sticky actions”/якоря для длинных форм Automation.
