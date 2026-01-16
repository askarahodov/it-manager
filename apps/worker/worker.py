"""Воркеры и периодические задачи.

MVP:
- периодический пересчёт состава динамических групп (через backend API)
- выполнение Ansible запусков из очереди Redis

Принципы безопасности:
- значения секретов запрашиваются у backend только через admin-only endpoint и
  используются в памяти для исполнения; в логи не пишем содержимое секретов.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import logging
import os
import queue
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import redis.asyncio as redis
from croniter import croniter

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

QUEUE_RUNS = "itmgr:runs:queue"
SCHEDULE_LOCK_PREFIX = "itmgr:schedule:lock:"

SECRET_REF_RE = re.compile(r"\\{\\{\\s*secret:(\\d+)\\s*\\}\\}")


@dataclass(frozen=True)
class InventoryBuildResult:
    text: str
    text_public: str
    agent_keys: list[tuple[Path, str | None]]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt_hs256(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    sig = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"


@dataclass(frozen=True)
class WorkerContext:
    secret_key: str
    backend_url: str
    redis_url: str
    recompute_interval: int
    schedule_poll_seconds: int
    rotation_poll_seconds: int
    lease_expire_poll_seconds: int
    run_timeout_seconds: int
    run_max_retries: int
    run_stale_seconds: int
    pending_requeue_seconds: int
    keep_sensitive_artifacts: bool
    use_ansible_runner: bool


def _ctx_from_env() -> WorkerContext:
    return WorkerContext(
        secret_key=os.environ.get("SECRET_KEY", "change-me"),
        backend_url=os.environ.get("BACKEND_URL", "http://backend:8000"),
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        recompute_interval=int(os.environ.get("WORKER_RECOMPUTE_INTERVAL_SECONDS", "60")),
        schedule_poll_seconds=int(os.environ.get("WORKER_SCHEDULE_POLL_SECONDS", "10")),
        rotation_poll_seconds=int(os.environ.get("WORKER_ROTATION_POLL_SECONDS", "60")),
        lease_expire_poll_seconds=int(os.environ.get("WORKER_LEASE_EXPIRE_POLL_SECONDS", "60")),
        run_timeout_seconds=int(os.environ.get("WORKER_RUN_TIMEOUT_SECONDS", "1800")),
        run_max_retries=int(os.environ.get("WORKER_RUN_MAX_RETRIES", "3")),
        run_stale_seconds=int(os.environ.get("WORKER_RUN_STALE_SECONDS", "3600")),
        pending_requeue_seconds=int(os.environ.get("WORKER_PENDING_REQUEUE_SECONDS", "120")),
        keep_sensitive_artifacts=os.environ.get("WORKER_KEEP_SENSITIVE_ARTIFACTS", "").lower() in {"1", "true", "yes"},
        use_ansible_runner=os.environ.get("WORKER_USE_ANSIBLE_RUNNER", "1").lower() in {"1", "true", "yes"},
    )


def _admin_token(secret_key: str, ttl_seconds: int = 300) -> str:
    now = int(time.time())
    return _jwt_hs256({"sub": "worker@it.local", "role": "admin", "exp": now + ttl_seconds}, secret_key)

def _make_request_id(prefix: str) -> str:
    """Генерирует request-id для корреляции логов между воркером и backend."""
    return f"{prefix}-{int(time.time() * 1000)}"

async def _backend_post(
    client: httpx.AsyncClient,
    token: str,
    path: str,
    json_body: dict | None = None,
    *,
    request_id: str | None = None,
    project_id: int | None = None,
) -> httpx.Response:
    url = client.base_url.join(path)
    headers = {"Authorization": f"Bearer {token}", "X-Request-Id": request_id or _make_request_id("worker")}
    if project_id is not None:
        headers["X-Project-Id"] = str(int(project_id))
    return await client.post(url, headers=headers, json=json_body)

async def _backend_get(
    client: httpx.AsyncClient,
    token: str,
    path: str,
    *,
    request_id: str | None = None,
    project_id: int | None = None,
) -> httpx.Response:
    url = client.base_url.join(path)
    headers = {"Authorization": f"Bearer {token}", "X-Request-Id": request_id or _make_request_id("worker")}
    if project_id is not None:
        headers["X-Project-Id"] = str(int(project_id))
    return await client.get(url, headers=headers)


async def _backend_delete(
    client: httpx.AsyncClient,
    token: str,
    path: str,
    *,
    request_id: str | None = None,
    project_id: int | None = None,
) -> httpx.Response:
    url = client.base_url.join(path)
    headers = {"Authorization": f"Bearer {token}", "X-Request-Id": request_id or _make_request_id("worker")}
    if project_id is not None:
        headers["X-Project-Id"] = str(int(project_id))
    return await client.delete(url, headers=headers)


async def _list_projects(client: httpx.AsyncClient, token: str) -> list[dict[str, Any]]:
    """Список проектов для обхода периодических задач.

    Если endpoint недоступен (например, миграция не применена) — fallback на default проект.
    """
    try:
        resp = await _backend_get(client, token, "/api/v1/projects/", request_id=_make_request_id("worker-projects"))
        if resp.status_code == 200:
            items = resp.json()
            if isinstance(items, list) and items:
                return [it for it in items if isinstance(it, dict) and "id" in it]
    except Exception:
        return [{"id": 1, "name": "default"}]
    return [{"id": 1, "name": "default"}]


async def recompute_dynamic_groups_loop(ctx: WorkerContext) -> None:
    logger.info("Dynamic groups loop started interval=%ss", ctx.recompute_interval)
    await asyncio.sleep(5)
    async with httpx.AsyncClient(base_url=ctx.backend_url, timeout=20) as client:
        while True:
            token = _admin_token(ctx.secret_key)
            try:
                projects = await _list_projects(client, token)
                ok = 0
                for pr in projects:
                    pid = int(pr.get("id") or 1)
                    resp = await _backend_post(
                        client,
                        token,
                        "/api/v1/groups/recompute-dynamic",
                        request_id=_make_request_id(f"worker-recompute-p{pid}"),
                        project_id=pid,
                    )
                    if resp.status_code == 204:
                        ok += 1
                    else:
                        logger.warning(
                            "Dynamic groups recompute failed project_id=%s status=%s body=%s",
                            pid,
                            resp.status_code,
                            resp.text[:200],
                        )
                if ok:
                    logger.info("Dynamic groups recomputed projects_ok=%s", ok)
                    next_sleep = ctx.recompute_interval
                else:
                    next_sleep = min(10, ctx.recompute_interval)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Dynamic groups recompute error: %s", exc)
                next_sleep = min(10, ctx.recompute_interval)
            await asyncio.sleep(next_sleep)


async def consume_runs_loop(ctx: WorkerContext) -> None:
    logger.info("Runs consumer started queue=%s", QUEUE_RUNS)
    r = redis.from_url(ctx.redis_url, decode_responses=True)

    async with httpx.AsyncClient(base_url=ctx.backend_url, timeout=30) as client:
        await asyncio.sleep(2)
        while True:
            item = await r.blpop(QUEUE_RUNS, timeout=5)
            if not item:
                continue
            _, run_id_str = item
            try:
                project_id = 1
                if ":" in run_id_str:
                    left, right = run_id_str.split(":", 1)
                    if left.isdigit() and right.isdigit():
                        project_id = int(left)
                        run_id = int(right)
                    else:
                        run_id = int(run_id_str)
                else:
                    run_id = int(run_id_str)
            except ValueError:
                logger.warning("Invalid run id in queue: %r", run_id_str)
                continue

            try:
                handled = await _execute_run(ctx, client, run_id, project_id=project_id)
                if not handled:
                    # временная ошибка: вернём в конец очереди, но ограничим число попыток
                    attempts = await _bump_attempt(r, run_id)
                    if attempts > ctx.run_max_retries:
                        token = _admin_token(ctx.secret_key)
                        await _append_log(
                            client,
                            token,
                            run_id,
                            f"==> abort: слишком много попыток ({attempts}) взять/выполнить запуск; помечаем как failed\n",
                            project_id=project_id,
                        )
                        await _set_status(client, token, run_id, "failed", project_id=project_id)
                        continue
                    await r.rpush(QUEUE_RUNS, f"{project_id}:{run_id}")
                    await asyncio.sleep(min(5, 1 + attempts))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Run execution crashed run_id=%s: %s", run_id, exc)
                attempts = await _bump_attempt(r, run_id)
                if attempts > ctx.run_max_retries:
                    token = _admin_token(ctx.secret_key)
                    await _append_log(
                        client,
                        token,
                        run_id,
                        f"==> abort: crash и превышен лимит попыток ({attempts}); помечаем как failed\n",
                        project_id=project_id,
                    )
                    await _set_status(client, token, run_id, "failed", project_id=project_id)
                    continue
                await r.rpush(QUEUE_RUNS, f"{project_id}:{run_id}")
                await asyncio.sleep(min(5, 1 + attempts))


async def schedule_runs_loop(ctx: WorkerContext) -> None:
    """Периодически создаёт новые JobRun по расписанию плейбуков.

    MVP: расписание хранится в `playbook.variables.__schedule`.
    """
    logger.info("Schedule loop started poll=%ss", ctx.schedule_poll_seconds)
    r = redis.from_url(ctx.redis_url, decode_responses=True)
    await asyncio.sleep(5)

    async with httpx.AsyncClient(base_url=ctx.backend_url, timeout=30) as client:
        while True:
            token = _admin_token(ctx.secret_key)
            try:
                now = datetime.now(timezone.utc)
                projects = await _list_projects(client, token)
                for pr in projects:
                    pid = int(pr.get("id") or 1)
                    resp = await _backend_get(
                        client,
                        token,
                        "/api/v1/playbooks/",
                        request_id=_make_request_id(f"worker-schedule-p{pid}"),
                        project_id=pid,
                    )
                    if resp.status_code != 200:
                        logger.warning("Schedule: cannot list playbooks project_id=%s status=%s", pid, resp.status_code)
                        continue
                    playbooks = resp.json()
                    for pb in playbooks:
                        schedule = (pb.get("schedule") or {})
                        if not isinstance(schedule, dict) or not schedule.get("enabled"):
                            continue
                        pb_id = int(pb["id"])
                        due_key = await _compute_due_key(schedule, now)
                        if due_key is None:
                            continue

                        lock_key = f"{SCHEDULE_LOCK_PREFIX}{pid}:{pb_id}:{due_key}"
                        got = await r.set(lock_key, "1", nx=True, ex=300)
                        if not got:
                            continue

                        payload = {
                            "host_ids": schedule.get("host_ids", []) or [],
                            "group_ids": schedule.get("group_ids", []) or [],
                            "extra_vars": schedule.get("extra_vars", {}) or {},
                            "dry_run": bool(schedule.get("dry_run")),
                        }
                        run_resp = await _backend_post(
                            client,
                            token,
                            f"/api/v1/playbooks/{pb_id}/run",
                            payload,
                            request_id=_make_request_id(f"worker-schedule-p{pid}-pb{pb_id}-{due_key}"),
                            project_id=pid,
                        )
                        if run_resp.status_code == 201:
                            logger.info(
                                "Scheduled run created project_id=%s playbook_id=%s run_id=%s",
                                pid,
                                pb_id,
                                run_resp.json().get("id"),
                            )
                            await _update_schedule_last_run(client, token, pb_id, schedule, now, project_id=pid)
                        else:
                            logger.warning(
                                "Scheduled run failed project_id=%s playbook_id=%s status=%s body=%s",
                                pid,
                                pb_id,
                                run_resp.status_code,
                                run_resp.text[:200],
                            )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Schedule loop error: %s", exc)

            await asyncio.sleep(ctx.schedule_poll_seconds)


async def secret_rotation_loop(ctx: WorkerContext) -> None:
    logger.info("Secret rotation loop started poll=%ss", ctx.rotation_poll_seconds)
    await asyncio.sleep(5)
    r = redis.from_url(ctx.redis_url, decode_responses=True)
    async with httpx.AsyncClient(base_url=ctx.backend_url, timeout=20) as client:
        while True:
            token = _admin_token(ctx.secret_key)
            now = datetime.utcnow()
            try:
                projects = await _list_projects(client, token)
                for pr in projects:
                    pid = int(pr.get("id") or 1)
                    resp = await _backend_get(
                        client,
                        token,
                        "/api/v1/secrets/",
                        request_id=_make_request_id(f"worker-secrets-p{pid}"),
                        project_id=pid,
                    )
                    if resp.status_code != 200:
                        logger.warning(
                            "Secrets list failed project_id=%s status=%s body=%s",
                            pid,
                            resp.status_code,
                            resp.text[:200],
                        )
                        continue
                    for sec in resp.json():
                        if not isinstance(sec, dict):
                            continue
                        sec_id = sec.get("id")
                        if not sec_id:
                            continue
                        expires_at = sec.get("expires_at")
                        if isinstance(expires_at, str) and expires_at:
                            exp_dt = None
                            try:
                                exp_dt = datetime.fromisoformat(expires_at)
                            except Exception:
                                exp_dt = None
                            if exp_dt and 0 <= (exp_dt - now).total_seconds() <= 7 * 86400:
                                key = f"itmgr:secret:expiring:{sec_id}:{exp_dt.date().isoformat()}"
                                if await r.setnx(key, "1"):
                                    await r.expire(key, 86400)
                                    await _backend_post(
                                        client,
                                        token,
                                        "/api/v1/notifications/emit",
                                        json_body={
                                            "event": "secret.expiring",
                                            "payload": {"secret_id": sec_id, "name": sec.get("name"), "expires_at": expires_at},
                                        },
                                        request_id=_make_request_id(f"worker-secret-expiring-{sec_id}"),
                                        project_id=pid,
                                    )

                        interval = sec.get("rotation_interval_days")
                        if not interval:
                            continue
                        next_rotated = sec.get("next_rotated_at")
                        if isinstance(next_rotated, str) and next_rotated:
                            try:
                                next_dt = datetime.fromisoformat(next_rotated)
                            except Exception:
                                next_dt = None
                        else:
                            next_dt = None
                        if next_dt and next_dt > now:
                            continue

                        if sec.get("type") not in {"password", "token"}:
                            continue
                        key = f"itmgr:secret:rotate:{sec_id}"
                        if not await r.setnx(key, "1"):
                            continue
                        await r.expire(key, 3600)
                        new_value = secrets.token_urlsafe(24)
                        rot = await _backend_post(
                            client,
                            token,
                            f"/api/v1/secrets/{sec_id}/rotate-apply",
                            json_body={"value": new_value},
                            request_id=_make_request_id(f"worker-secret-rotate-apply-{sec_id}"),
                            project_id=pid,
                        )
                        if rot.status_code == 400:
                            rot = await _backend_post(
                                client,
                                token,
                                f"/api/v1/secrets/{sec_id}/rotate",
                                json_body={"value": new_value},
                                request_id=_make_request_id(f"worker-secret-rotate-{sec_id}"),
                                project_id=pid,
                            )
                        if rot.status_code not in {200, 201}:
                            logger.warning(
                                "Secret rotate failed secret_id=%s status=%s body=%s",
                                sec_id,
                                rot.status_code,
                                rot.text[:200],
                            )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Secret rotation loop error: %s", exc)
            await asyncio.sleep(ctx.rotation_poll_seconds)


async def secret_lease_expire_loop(ctx: WorkerContext) -> None:
    logger.info("Secret lease expire loop started poll=%ss", ctx.lease_expire_poll_seconds)
    await asyncio.sleep(5)
    async with httpx.AsyncClient(base_url=ctx.backend_url, timeout=20) as client:
        while True:
            token = _admin_token(ctx.secret_key)
            try:
                resp = await _backend_post(
                    client,
                    token,
                    "/api/v1/secrets/leases/expire",
                    request_id=_make_request_id("worker-lease-expire"),
                )
                if resp.status_code != 204:
                    logger.warning(
                        "Lease expire failed status=%s body=%s",
                        resp.status_code,
                        resp.text[:200],
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Lease expire loop error: %s", exc)
            await asyncio.sleep(ctx.lease_expire_poll_seconds)

async def stale_runs_watchdog_loop(ctx: WorkerContext) -> None:
    """Watchdog для зависших запусков.

    Если воркер упал после claim, запуск может остаться в status=running навсегда.
    В MVP делаем best-effort: периодически проверяем такие runs и помечаем failed.
    """
    logger.info("Stale runs watchdog started stale_after=%ss", ctx.run_stale_seconds)
    await asyncio.sleep(10)
    r = redis.from_url(ctx.redis_url, decode_responses=True)
    async with httpx.AsyncClient(base_url=ctx.backend_url, timeout=30) as client:
        while True:
            token = _admin_token(ctx.secret_key)
            try:
                now = datetime.now(timezone.utc)
                projects = await _list_projects(client, token)
                for pr in projects:
                    pid = int(pr.get("id") or 1)
                    resp = await _backend_get(
                        client,
                        token,
                        "/api/v1/runs/",
                        request_id=_make_request_id(f"worker-watchdog-p{pid}"),
                        project_id=pid,
                    )
                    if resp.status_code != 200:
                        continue
                    for run in resp.json():
                        status = run.get("status")
                        if status not in {"running", "pending"}:
                            continue
                        created_at = run.get("created_at")
                        started_at = run.get("started_at")
                        try:
                            created = datetime.fromisoformat(created_at) if created_at else None
                        except Exception:
                            created = None
                        if created and created.tzinfo is None:
                            created = created.replace(tzinfo=timezone.utc)
                        try:
                            started = datetime.fromisoformat(started_at) if started_at else None
                        except Exception:
                            started = None
                        if started and started.tzinfo is None:
                            started = started.replace(tzinfo=timezone.utc)

                        if status == "pending":
                            if not created:
                                continue
                            age = (now - created).total_seconds()
                            if age < ctx.pending_requeue_seconds:
                                continue
                            snapshot = run.get("target_snapshot") or {}
                            approval_status = snapshot.get("approval_status")
                            if approval_status == "pending" or snapshot.get("approval_id"):
                                continue
                            run_id = int(run["id"])
                            lock_key = f"itmgr:runs:requeue:{pid}:{run_id}"
                            got = await r.set(lock_key, "1", nx=True, ex=300)
                            if not got:
                                continue
                            await r.lpush(QUEUE_RUNS, f"{pid}:{run_id}")
                            logger.warning("Requeued pending run run_id=%s project_id=%s age=%ss", run_id, pid, int(age))
                            continue

                        if status != "running":
                            continue
                        if not started:
                            continue
                        age = (now - started).total_seconds()
                        if age < ctx.run_stale_seconds:
                            continue
                        run_id = int(run["id"])
                        rid = _make_request_id(f"worker-watchdog-p{pid}-run-{run_id}")
                        await _append_log(
                            client,
                            token,
                            run_id,
                            f"==> watchdog: запуск завис (running более {int(age)}s), помечаем как failed\n",
                            request_id=rid,
                            project_id=pid,
                        )
                        await _set_status(client, token, run_id, "failed", request_id=rid, project_id=pid)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Stale watchdog error: %s", exc)
            await asyncio.sleep(30)


async def _execute_run(
    ctx: WorkerContext,
    client: httpx.AsyncClient,
    run_id: int,
    *,
    project_id: int,
) -> bool:
    token = _admin_token(ctx.secret_key)
    rid = _make_request_id(f"worker-run-{run_id}")
    claim = await _backend_post(client, token, f"/api/v1/runs/{run_id}/claim", request_id=rid, project_id=project_id)
    if claim.status_code != 200:
        logger.warning("Cannot claim run_id=%s status=%s body=%s", run_id, claim.status_code, claim.text[:200])
        # 5xx: временная ошибка, можно попробовать позже (requeue).
        # 4xx/409: не имеет смысла повторять (уже взят/завершён/не найден) — считаем обработанным.
        return claim.status_code < 500

    payload = claim.json()
    run = payload["run"]
    playbook = payload["playbook"]
    if int(run.get("project_id") or project_id) != int(project_id):
        logger.warning("Claim project mismatch run_id=%s expected_project_id=%s got=%s", run_id, project_id, run.get("project_id"))
        return True

    await _append_log(
        client,
        token,
        run_id,
        f"==> start run_id={run_id} playbook={playbook.get('name')}\n",
        request_id=rid,
        project_id=project_id,
    )

    stored_content = playbook.get("stored_content")
    if not stored_content:
        await _append_log(
            client,
            token,
            run_id,
            "Ошибка: плейбук пустой (stored_content отсутствует)\n",
            request_id=rid,
            project_id=project_id,
        )
        await _set_status(client, token, run_id, "failed", request_id=rid, project_id=project_id)
        return True

    targets = run.get("target_snapshot") or {}
    hosts = targets.get("hosts") or []
    if not hosts:
        await _append_log(
            client,
            token,
            run_id,
            "Ошибка: цели отсутствуют (hosts пуст)\n",
            request_id=rid,
            project_id=project_id,
        )
        await _set_status(client, token, run_id, "failed", request_id=rid, project_id=project_id)
        return True

    run_dir = Path("/var/ansible") / "runs" / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    playbook_path = run_dir / "playbook.yml"
    inventory_path = run_dir / "inventory.ini"
    public_inventory_path = run_dir / "inventory.public.ini"
    run_log_path = run_dir / "run.log"

    playbook_path.write_text(stored_content, encoding="utf-8")

    # vars: playbook.variables + run.extra_vars
    merged_vars: dict[str, Any] = {}
    merged_vars.update(playbook.get("variables") or {})
    merged_vars.update(targets.get("extra_vars") or {})
    merged_vars = await _resolve_secret_refs(client, token, merged_vars, request_id=rid, project_id=project_id)

    inventory_text = await _build_inventory(client, token, hosts, run_dir, request_id=rid, project_id=project_id)
    inventory_path.write_text(inventory_text.text, encoding="utf-8")
    os.chmod(inventory_path, 0o600)
    public_inventory_path.write_text(inventory_text.text_public, encoding="utf-8")
    os.chmod(public_inventory_path, 0o644)

    dry_run = bool(targets.get("dry_run"))

    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    env["PYTHONUNBUFFERED"] = "1"
    # на всякий случай — не используем stdout_callback, чтобы не ломать парсинг

    agent_started = False
    if inventory_text.agent_keys:
        await _start_ssh_agent(env)
        agent_started = True
        for key_path, passphrase in inventory_text.agent_keys:
            await _ssh_add_key(env, key_path, passphrase)

    facts_run = bool(targets.get("facts_run"))
    facts_host_id = None
    if facts_run and len(hosts) == 1:
        facts_host_id = hosts[0].get("id")

    used_runner_status: str | None = None
    try:
        if ctx.use_ansible_runner:
            used_runner_status = await _run_with_ansible_runner(
                ctx,
                client,
                token,
                run_id,
                run_dir,
                playbook_path,
                inventory_path,
                merged_vars,
                dry_run=dry_run,
                env=env,
                request_id=rid,
                run_log_path=run_log_path,
                project_id=project_id,
                facts_run=facts_run,
                facts_host_id=facts_host_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("ansible-runner failed, fallback to ansible-playbook run_id=%s: %s", run_id, exc)
        used_runner_status = None

    if used_runner_status:
        # статус и логи выставлены внутри runner.
        await _finalize_rotation(
            client,
            token,
            run_id=run_id,
            project_id=project_id,
            status_value=used_runner_status,
            targets=targets,
            request_id=rid,
        )
        return True

    if facts_run:
        await _append_log(
            client,
            token,
            run_id,
            "==> facts: ansible-runner недоступен, факты не сохранены\n",
            request_id=rid,
            project_id=project_id,
        )

    # Fallback: прямой запуск ansible-playbook (MVP)
    extra_vars_path = run_dir / "extra_vars.json"
    extra_vars_path.write_text(json.dumps(merged_vars, ensure_ascii=False), encoding="utf-8")
    os.chmod(extra_vars_path, 0o600)

    args = [
        "ansible-playbook",
        "-i",
        str(inventory_path),
        str(playbook_path),
        "--ssh-common-args",
        "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
        "--extra-vars",
        f"@{extra_vars_path}",
    ]
    if dry_run:
        args += ["--check"]

    await _append_log(
        client,
        token,
        run_id,
        f"==> exec: {' '.join(args)}\n",
        request_id=rid,
        project_id=project_id,
    )
    _append_file(run_log_path, f"==> exec: {' '.join(args)}\n")

    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(run_dir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        assert proc.stdout is not None
        buffer: list[str] = []
        last_flush = time.time()
        deadline = time.monotonic() + max(5, ctx.run_timeout_seconds)
        timed_out = False

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=min(1.0, remaining))
            except asyncio.TimeoutError:
                # процесс всё ещё работает, ждём дальше
                continue
            if not line:
                break
            text = line.decode("utf-8", errors="ignore")
            buffer.append(text)

            # flush каждые ~1 сек или по размеру
            if len(buffer) >= 50 or (time.time() - last_flush) >= 1:
                chunk = "".join(buffer)
                await _append_log(client, token, run_id, chunk, request_id=rid, project_id=project_id)
                _append_file(run_log_path, chunk)
                buffer.clear()
                last_flush = time.time()

        if buffer:
            chunk = "".join(buffer)
            await _append_log(client, token, run_id, chunk, request_id=rid, project_id=project_id)
            _append_file(run_log_path, chunk)

        if timed_out:
            await _append_log(
                client,
                token,
                run_id,
                f"==> timeout: превышен лимит {ctx.run_timeout_seconds}s, останавливаем процесс\n",
                request_id=rid,
                project_id=project_id,
            )
            _append_file(run_log_path, f"==> timeout: превышен лимит {ctx.run_timeout_seconds}s, останавливаем процесс\n")
            proc.kill()
            await proc.wait()
            status_value = "failed"
            await _set_status(client, token, run_id, status_value, request_id=rid, project_id=project_id)
            await _finalize_rotation(
                client,
                token,
                run_id=run_id,
                project_id=project_id,
                status_value=status_value,
                targets=targets,
                request_id=rid,
            )
        else:
            code = await proc.wait()
            if code == 0:
                status_value = "success"
                await _append_log(client, token, run_id, "==> done: success\n", request_id=rid, project_id=project_id)
                _append_file(run_log_path, "==> done: success\n")
                await _set_status(client, token, run_id, status_value, request_id=rid, project_id=project_id)
            else:
                status_value = "failed"
                await _append_log(
                    client,
                    token,
                    run_id,
                    f"==> done: failed (exit={code})\n",
                    request_id=rid,
                    project_id=project_id,
                )
                _append_file(run_log_path, f"==> done: failed (exit={code})\n")
                await _set_status(client, token, run_id, status_value, request_id=rid, project_id=project_id)
            await _finalize_rotation(
                client,
                token,
                run_id=run_id,
                project_id=project_id,
                status_value=status_value,
                targets=targets,
                request_id=rid,
            )
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        if agent_started:
            await _stop_ssh_agent(env)
        if not ctx.keep_sensitive_artifacts:
            _cleanup_sensitive_artifacts(run_dir)
    return True


async def _run_with_ansible_runner(
    ctx: WorkerContext,
    client: httpx.AsyncClient,
    token: str,
    run_id: int,
    run_dir: Path,
    playbook_path: Path,
    inventory_path: Path,
    extravars: dict[str, Any],
    *,
    dry_run: bool,
    env: dict[str, str],
    request_id: str,
    run_log_path: Path,
    project_id: int,
    facts_run: bool,
    facts_host_id: int | None,
) -> str | None:
    """Запуск плейбука через ansible-runner (с event stream).

    Возвращает итоговый статус (success/failed) если runner отработал,
    или None — если runner недоступен/не должен использоваться.
    """
    try:
        import ansible_runner  # type: ignore
    except Exception:
        return None

    private_dir = run_dir / "runner"
    (private_dir / "project").mkdir(parents=True, exist_ok=True)
    (private_dir / "inventory").mkdir(parents=True, exist_ok=True)

    # Копируем входные файлы (playbook и inventory) в структуру runner.
    (private_dir / "project" / "playbook.yml").write_text(playbook_path.read_text(encoding="utf-8"), encoding="utf-8")
    (private_dir / "inventory" / "hosts").write_text(inventory_path.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(private_dir / "inventory" / "hosts", 0o600)

    cmdline = "--ssh-common-args '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'"
    if dry_run:
        cmdline += " --check"

    out_q: "queue.Queue[str]" = queue.Queue()

    facts_holder: list[dict[str, Any] | None] = [None]

    def event_handler(event: dict[str, Any]) -> None:
        if not facts_run:
            pass
        elif event.get("event") == "runner_on_ok":
            data = event.get("event_data") or {}
            if data.get("task") == "Gathering Facts":
                res = data.get("res") or {}
                facts = res.get("ansible_facts")
                if isinstance(facts, dict):
                    facts_holder[0] = facts

        stdout = event.get("stdout")
        if not stdout:
            return
        try:
            out_q.put_nowait(str(stdout) + "\n")
        except Exception:
            return

    await _append_log(client, token, run_id, "==> exec: ansible-runner\n", request_id=request_id, project_id=project_id)
    _append_file(run_log_path, "==> exec: ansible-runner\n")

    # Запускаем runner асинхронно (thread) и параллельно стримим stdout в backend.
    thread, runner = ansible_runner.interface.run_async(  # type: ignore[attr-defined]
        private_data_dir=str(private_dir),
        playbook="playbook.yml",
        inventory="hosts",
        extravars=extravars,
        envvars={
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "PYTHONUNBUFFERED": "1",
            **{k: v for k, v in env.items() if k in {"SSH_AUTH_SOCK", "SSH_AGENT_PID"}},
        },
        cmdline=cmdline,
        quiet=True,
        event_handler=event_handler,
    )

    deadline = time.monotonic() + max(5, ctx.run_timeout_seconds)
    while thread.is_alive():
        # flush queue
        chunk_parts: list[str] = []
        try:
            while True:
                chunk_parts.append(out_q.get_nowait())
        except queue.Empty:
            pass
        if chunk_parts:
            chunk = "".join(chunk_parts)
            await _append_log(client, token, run_id, chunk, request_id=request_id, project_id=project_id)
            _append_file(run_log_path, chunk)

        if time.monotonic() > deadline:
            await _append_log(
                client,
                token,
                run_id,
                f"==> timeout: превышен лимит {ctx.run_timeout_seconds}s, отменяем ansible-runner\n",
                request_id=request_id,
                project_id=project_id,
            )
            _append_file(run_log_path, f"==> timeout: превышен лимит {ctx.run_timeout_seconds}s, отменяем ansible-runner\n")
            try:
                runner.cancel()  # type: ignore[attr-defined]
            except Exception:
                pass
            break
        await asyncio.sleep(0.5)

    # Финальный flush
    chunk_parts = []
    try:
        while True:
            chunk_parts.append(out_q.get_nowait())
    except queue.Empty:
        pass
    if chunk_parts:
        chunk = "".join(chunk_parts)
        await _append_log(client, token, run_id, chunk, request_id=request_id, project_id=project_id)
        _append_file(run_log_path, chunk)

    thread.join(timeout=5)
    rc = getattr(runner, "rc", None)
    status_value = "success" if rc == 0 else "failed"
    await _append_log(
        client,
        token,
        run_id,
        f"==> done: {status_value} (rc={rc})\n",
        request_id=request_id,
        project_id=project_id,
    )
    _append_file(run_log_path, f"==> done: {status_value} (rc={rc})\n")
    await _set_status(client, token, run_id, status_value, request_id=request_id, project_id=project_id)

    # Сохраняем безопасное summary
    try:
        summary = {"runner": "ansible-runner", "rc": rc, "status": status_value}
        (run_dir / "runner.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    if facts_run and facts_host_id and facts_holder[0]:
        await _backend_post(
            client,
            token,
            f"/api/v1/hosts/{facts_host_id}/facts",
            {"facts": facts_holder[0]},
            request_id=request_id,
            project_id=project_id,
        )

    if not ctx.keep_sensitive_artifacts:
        # runner может сохранить артефакты, иногда содержащие входные данные; удаляем best-effort
        try:
            import shutil

            shutil.rmtree(private_dir, ignore_errors=True)
        except Exception:
            pass
    return status_value


async def _bump_attempt(r: "redis.Redis", run_id: int) -> int:
    """Счётчик попыток обработки run_id.

    Храним в Redis, чтобы переживать рестарты воркера.
    """
    key = f"itmgr:runs:attempt:{run_id}"
    attempts = int(await r.incr(key))
    # TTL достаточно большой, чтобы покрыть ретраи; при успехе ключ не мешает.
    await r.expire(key, 3600)
    return attempts


async def _append_log(
    client: httpx.AsyncClient,
    token: str,
    run_id: int,
    chunk: str,
    *,
    request_id: str | None = None,
    project_id: int | None = None,
) -> None:
    if not chunk:
        return
    await _backend_post(
        client,
        token,
        f"/api/v1/runs/{run_id}/append-log",
        {"chunk": chunk},
        request_id=request_id or _make_request_id(f"worker-run-{run_id}"),
        project_id=project_id,
    )


async def _set_status(
    client: httpx.AsyncClient,
    token: str,
    run_id: int,
    status_value: str,
    *,
    request_id: str | None = None,
    project_id: int | None = None,
) -> None:
    finished = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    await _backend_post(
        client,
        token,
        f"/api/v1/runs/{run_id}/set-status",
        {"status": status_value, "finished_at": finished},
        request_id=request_id or _make_request_id(f"worker-run-{run_id}"),
        project_id=project_id,
    )


async def _finalize_rotation(
    client: httpx.AsyncClient,
    token: str,
    *,
    run_id: int,
    project_id: int,
    status_value: str,
    targets: dict[str, Any],
    request_id: str,
) -> None:
    rotation = targets.get("rotation") or {}
    target_secret_id = rotation.get("target_secret_id")
    temp_secret_id = rotation.get("temp_secret_id")
    if not target_secret_id or not temp_secret_id:
        return

    if status_value == "success":
        reveal = await _backend_post(
            client,
            token,
            f"/api/v1/secrets/{int(temp_secret_id)}/reveal-internal",
            request_id=f"{request_id}-rotation-reveal",
            project_id=project_id,
        )
        if reveal.status_code == 200:
            payload = reveal.json()
            rotate_payload: dict[str, Any] = {"value": payload.get("value", "")}
            if payload.get("passphrase"):
                rotate_payload["passphrase"] = payload.get("passphrase")
            rotate = await _backend_post(
                client,
                token,
                f"/api/v1/secrets/{int(target_secret_id)}/rotate",
                json_body=rotate_payload,
                request_id=f"{request_id}-rotation-apply",
                project_id=project_id,
            )
            if rotate.status_code not in {200, 201}:
                logger.warning(
                    "Rotation apply failed run_id=%s secret_id=%s status=%s body=%s",
                    run_id,
                    target_secret_id,
                    rotate.status_code,
                    rotate.text[:200],
                )
        else:
            logger.warning(
                "Rotation reveal failed run_id=%s temp_secret_id=%s status=%s body=%s",
                run_id,
                temp_secret_id,
                reveal.status_code,
                reveal.text[:200],
            )

    delete_resp = await _backend_delete(
        client,
        token,
        f"/api/v1/secrets/{int(temp_secret_id)}",
        request_id=f"{request_id}-rotation-clean",
        project_id=project_id,
    )
    if delete_resp.status_code not in {200, 204}:
        logger.warning(
            "Rotation cleanup failed run_id=%s temp_secret_id=%s status=%s body=%s",
            run_id,
            temp_secret_id,
            delete_resp.status_code,
            delete_resp.text[:200],
        )


async def _reveal_secret(
    client: httpx.AsyncClient,
    token: str,
    secret_id: int,
    *,
    request_id: str | None = None,
    project_id: int | None = None,
) -> dict[str, Any]:
    resp = await _backend_post(
        client,
        token,
        f"/api/v1/secrets/{secret_id}/reveal-internal",
        request_id=request_id or _make_request_id(f"worker-secret-{secret_id}"),
        project_id=project_id,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Не удалось раскрыть secret:{secret_id} (status={resp.status_code})")
    return resp.json()


async def _resolve_secret_refs(
    client: httpx.AsyncClient, token: str, data: Any, *, request_id: str | None = None, project_id: int | None = None
) -> Any:
    cache: dict[int, dict[str, Any]] = {}

    async def resolve_value(value: Any) -> Any:
        if isinstance(value, str):
            matches = list(SECRET_REF_RE.finditer(value))
            if not matches:
                return value
            result = value
            for m in matches:
                sid = int(m.group(1))
                if sid not in cache:
                    cache[sid] = await _reveal_secret(client, token, sid, request_id=request_id, project_id=project_id)
                secret_value = cache[sid].get("value", "")
                result = result.replace(m.group(0), str(secret_value))
            return result
        if isinstance(value, list):
            return [await resolve_value(v) for v in value]
        if isinstance(value, dict):
            return {k: await resolve_value(v) for k, v in value.items()}
        return value

    return await resolve_value(data)


async def _build_inventory(
    client: httpx.AsyncClient,
    token: str,
    hosts: list[dict[str, Any]],
    run_dir: Path,
    *,
    request_id: str | None = None,
    project_id: int | None = None,
) -> InventoryBuildResult:
    lines = ["[all]"]
    public_lines = ["[all]"]
    agent_keys: list[tuple[Path, str | None]] = []
    for item in hosts:
        host_id = int(item["id"])
        name = str(item.get("name") or f"host-{host_id}")
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
        hostname = str(item["hostname"])
        port = int(item.get("port") or 22)
        username = str(item.get("username") or "root")

        parts = [
            safe_name,
            f"ansible_host={hostname}",
            f"ansible_port={port}",
            f"ansible_user={username}",
        ]
        public_lines.append(" ".join(parts))

        cred_id = item.get("credential_id")
        if cred_id:
            secret = await _backend_get(
                client, token, f"/api/v1/secrets/{int(cred_id)}", request_id=request_id, project_id=project_id
            )
            if secret.status_code == 200:
                secret_meta = secret.json()
                secret_type = secret_meta.get("type")
                if secret_type == "password":
                    revealed = await _reveal_secret(client, token, int(cred_id), request_id=request_id, project_id=project_id)
                    parts.append(f"ansible_password={_escape_ini(revealed.get('value',''))}")
                elif secret_type == "private_key":
                    revealed = await _reveal_secret(client, token, int(cred_id), request_id=request_id, project_id=project_id)
                    key_path = run_dir / f"key_{host_id}.pem"
                    key_path.write_text(revealed.get("value", ""), encoding="utf-8")
                    os.chmod(key_path, 0o600)
                    passphrase = revealed.get("passphrase")
                    if passphrase:
                        # Для ключей с passphrase используем ssh-agent + ssh-add.
                        agent_keys.append((key_path, str(passphrase)))
                    else:
                        # Ключ без passphrase можно передать напрямую.
                        parts.append(f"ansible_ssh_private_key_file={key_path}")
        lines.append(" ".join(parts))
    lines.append("")
    public_lines.append("")
    return InventoryBuildResult(text="\n".join(lines), text_public="\n".join(public_lines), agent_keys=agent_keys)


def _escape_ini(value: str) -> str:
    return value.replace(" ", "\\ ").replace("\n", "").replace("\r", "")


def _append_file(path: Path, chunk: str) -> None:
    if not chunk:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="ignore") as f:
        f.write(chunk)


def _cleanup_sensitive_artifacts(run_dir: Path) -> None:
    """Удаляет файлы, которые могут содержать секреты.

    По умолчанию не оставляем на диске:
    - inventory.ini (ansible_password / ключи)
    - extra_vars.json (секреты после resolve)
    - key_*.pem
    """
    try:
        (run_dir / "inventory.ini").unlink(missing_ok=True)
        (run_dir / "extra_vars.json").unlink(missing_ok=True)
        for key in run_dir.glob("key_*.pem"):
            try:
                key.unlink()
            except Exception:
                pass
    except Exception:
        # best-effort
        return


async def _start_ssh_agent(env: dict[str, str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ssh-agent",
        "-s",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ssh-agent failed: {err.decode(errors='ignore')}")
    text = out.decode("utf-8", errors="ignore")
    # SSH_AUTH_SOCK=...; export SSH_AUTH_SOCK; SSH_AGENT_PID=...; export SSH_AGENT_PID;
    for part in text.split(";"):
        part = part.strip()
        if part.startswith("SSH_AUTH_SOCK="):
            env["SSH_AUTH_SOCK"] = part.split("=", 1)[1]
        if part.startswith("SSH_AGENT_PID="):
            env["SSH_AGENT_PID"] = part.split("=", 1)[1]


async def _ssh_add_key(env: dict[str, str], key_path: Path, passphrase: str | None) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ssh-add",
        str(key_path),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if proc.stdin and passphrase is not None:
        proc.stdin.write((passphrase + "\n").encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ssh-add failed: {err.decode(errors='ignore') or out.decode(errors='ignore')}")


async def _stop_ssh_agent(env: dict[str, str]) -> None:
    # best-effort
    try:
        await asyncio.create_subprocess_exec("ssh-agent", "-k", env=env)
    except Exception:
        pass


async def main() -> None:
    ctx = _ctx_from_env()
    logger.info("Worker started backend_url=%s redis_url=%s", ctx.backend_url, ctx.redis_url)
    await asyncio.gather(
        recompute_dynamic_groups_loop(ctx),
        consume_runs_loop(ctx),
        schedule_runs_loop(ctx),
        stale_runs_watchdog_loop(ctx),
        secret_rotation_loop(ctx),
        secret_lease_expire_loop(ctx),
    )


async def _compute_due_key(schedule: dict[str, Any], now: datetime) -> str | None:
    # last_run_at — в ISO (UTC, без tz) или None
    last_run = schedule.get("last_run_at")
    last_dt: datetime | None = None
    if isinstance(last_run, str) and last_run:
        try:
            last_dt = datetime.fromisoformat(last_run)
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        except Exception:
            last_dt = None

    schedule_type = schedule.get("type", "interval")
    value = str(schedule.get("value", "300"))
    if schedule_type == "interval":
        try:
            seconds = int(value)
        except ValueError:
            return None
        seconds = max(10, min(seconds, 24 * 3600))
        now_utc = now.astimezone(timezone.utc)
        if last_dt is None or (now_utc - last_dt).total_seconds() >= seconds:
            bucket = int(now_utc.timestamp()) // seconds
            return f"i{bucket}"
        return None

    if schedule_type == "cron":
        # Исполняем "по ближайшему прошлому срабатыванию", если оно позже last_run_at.
        now_naive = now.astimezone(timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
        last_naive = last_dt.astimezone(timezone.utc).replace(tzinfo=None) if last_dt else None
        try:
            it = croniter(value, now_naive)
            prev = it.get_prev(datetime)
        except Exception:
            return None
        if last_naive is None or prev > last_naive:
            # ключ по минуте прошлого срабатывания
            return prev.strftime("%Y%m%d%H%M")
        return None
    return None


async def _update_schedule_last_run(
    client: httpx.AsyncClient,
    token: str,
    playbook_id: int,
    schedule: dict[str, Any],
    now: datetime,
    *,
    project_id: int,
) -> None:
    try:
        schedule2 = dict(schedule)
        schedule2["last_run_at"] = now.replace(tzinfo=None).isoformat()
        url = client.base_url.join(f"/api/v1/playbooks/{playbook_id}")
        await client.put(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Request-Id": _make_request_id(f"worker-schedule-p{project_id}-pb{playbook_id}"),
                "X-Project-Id": str(int(project_id)),
            },
            json={"schedule": schedule2},
        )
    except Exception:
        return


if __name__ == "__main__":
    asyncio.run(main())
