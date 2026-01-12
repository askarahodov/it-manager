# ADR 0001: Стек IT Manager

## Статус
Проект в фазе Bootstrap (draft).

## Контекст
Нужен полный стек для удобного бэкенда, производительного фронта, безопасного доступа и автоматизации Ansible. Платформа должна быть контейнеризуемой и хорошо документируемой.

## Решение
- FastAPI + SQLAlchemy + Alembic обеспечивают асинхронную логтику, OpenAPI и простую интеграцию с asyncssh/ansible-runner.
- PostgreSQL дает надежное хранилище для иерархических объектов и секретов.
- React + Vite подходит для админки с быстрым перезагрузком; xterm.js реализует браузерный терминал.
- Worker-контейнер на Python хостит scheduler, ansible-runner и job-очередь (APScheduler/Bull в будущем).
- Docker Compose связывает сервисы, поставляя готовый стек для команды.

## Последствия
- Быстрый development cycle благодаря FastAPI и Vite.
- Легкая интеграция JWT, RBAC и secrets vault.
- Позже легко добавить worker-очередь (Celery/RQ) и WebSocket-пайп SSH.
