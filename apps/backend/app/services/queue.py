"""Очередь задач через Redis.

MVP: используем список Redis с BLPOP/LPUSH.
"""

from __future__ import annotations

import logging

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

QUEUE_RUNS = "itmgr:runs:queue"

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis  # noqa: PLW0603
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def enqueue_run(run_id: int, *, project_id: int | None = None) -> None:
    client = get_redis()
    payload = f"{int(project_id)}:{int(run_id)}" if project_id is not None else str(run_id)
    await client.lpush(QUEUE_RUNS, payload)
    logger.info("Run enqueued run_id=%s project_id=%s", run_id, project_id)
