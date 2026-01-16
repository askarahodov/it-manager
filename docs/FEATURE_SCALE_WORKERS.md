# Feature: Multiple Workers + Distributed Locks

## Цель
Обеспечить горизонтальное масштабирование воркеров и устранить дубли запусков.

## Основные механизмы
- Redis‑lock для задач (run_id, schedule due_key).
- Lease‑механизм для "claim" run‑ов: worker обновляет heartbeat.
- Watchdog для зависших run‑ов.

## Изменения
- Queue: перейти на список/stream с ack (Redis Streams или RQ/Celery).
- Lock key strategy: `itmgr:lock:run:{id}` с TTL.
- Idempotency: запрет повторного выполнения одного run.

## API/Worker
- `POST /api/v1/runs/{id}/claim` возвращает lease info.
- Новый endpoint `POST /api/v1/runs/{id}/heartbeat`.

## Метрики
- active_workers, queue_depth, run_latency, lock_contention.

## Риски
- Потеря run при смерти воркера → нужно requeue.
- Конкуренция scheduler/worker — требует строгих lock‑правил.
