from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalRequest, ApprovalStatus, Host, JobRun, JobStatus, Playbook, PlaybookTrigger, Secret
from app.services.audit import audit_log
from app.services.queue import enqueue_run


def _match_trigger_filters(filters: dict[str, Any], host: Host) -> bool:
    if not filters:
        return True
    environments = filters.get("environments")
    if isinstance(environments, list) and environments:
        if host.environment not in environments:
            return False
    tags = filters.get("tags")
    if isinstance(tags, dict):
        host_tags = host.tags or {}
        for key, value in tags.items():
            if host_tags.get(key) != value:
                return False
    return True


def _match_secret_filters(filters: dict[str, Any], secret: Secret) -> bool:
    if not filters:
        return True
    types = filters.get("types")
    if isinstance(types, list) and types:
        if secret.type not in types:
            return False
    scopes = filters.get("scopes")
    if isinstance(scopes, list) and scopes:
        if secret.scope not in scopes:
            return False
    tags = filters.get("tags")
    if isinstance(tags, dict):
        secret_tags = secret.tags or {}
        for key, value in tags.items():
            if secret_tags.get(key) != value:
                return False
    return True


async def _create_run_for_trigger(
    db: AsyncSession,
    playbook: Playbook,
    hosts: list[Host],
    extra_vars: dict[str, Any],
    trigger_type: str,
) -> JobRun:
    snapshot_hosts = [
        {
            "id": host.id,
            "name": host.name,
            "hostname": host.hostname,
            "port": host.port,
            "username": host.username,
            "credential_id": host.credential_id,
        }
        for host in hosts
    ]
    requires_approval = any(h.environment == "prod" for h in hosts)
    run = JobRun(
        project_id=playbook.project_id,
        playbook_id=playbook.id,
        triggered_by=f"trigger:{trigger_type}",
        status=JobStatus.pending,
        target_snapshot={
            "hosts": snapshot_hosts,
            "group_ids": [],
            "host_ids": [host.id for host in hosts],
            "extra_vars": extra_vars,
            "dry_run": False,
            "params_before": {},
            "params_after": extra_vars,
            "trigger": trigger_type,
        },
        logs="",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    if requires_approval:
        approval = ApprovalRequest(
            project_id=playbook.project_id,
            run_id=run.id,
            requested_by=None,
            status=ApprovalStatus.pending,
        )
        db.add(approval)
        run.target_snapshot["approval_status"] = "pending"
        await db.commit()
        await db.refresh(approval)
        run.target_snapshot["approval_id"] = approval.id
        await db.commit()
        await audit_log(
            db,
            project_id=playbook.project_id,
            actor="trigger",
            actor_role="trigger",
            action="run.create_trigger_requires_approval",
            entity_type="run",
            entity_id=run.id,
            meta={"playbook_id": playbook.id, "targets": len(snapshot_hosts), "approval_id": approval.id, "trigger": trigger_type},
        )
    else:
        await enqueue_run(run.id, project_id=playbook.project_id)
        await audit_log(
            db,
            project_id=playbook.project_id,
            actor="trigger",
            actor_role="trigger",
            action="run.create_trigger",
            entity_type="run",
            entity_id=run.id,
            meta={"playbook_id": playbook.id, "targets": len(snapshot_hosts), "trigger": trigger_type},
        )
    return run


async def dispatch_host_triggers(db: AsyncSession, host: Host, trigger_type: str) -> None:
    query = await db.execute(
        select(PlaybookTrigger)
        .where(PlaybookTrigger.project_id == host.project_id)
        .where(PlaybookTrigger.enabled.is_(True))
        .where(PlaybookTrigger.type == trigger_type)
    )
    triggers = query.scalars().all()
    for trigger in triggers:
        playbook = await db.get(Playbook, trigger.playbook_id)
        if not playbook or playbook.project_id != host.project_id:
            continue
        filters = trigger.filters or {}
        if not _match_trigger_filters(filters, host):
            continue
        await _create_run_for_trigger(db, playbook, [host], trigger.extra_vars or {}, trigger_type)


async def dispatch_secret_triggers(db: AsyncSession, secret: Secret, project_id: int) -> None:
    query = await db.execute(
        select(PlaybookTrigger)
        .where(PlaybookTrigger.project_id == project_id)
        .where(PlaybookTrigger.enabled.is_(True))
        .where(PlaybookTrigger.type == "secret_rotated")
    )
    triggers = query.scalars().all()
    if not triggers:
        return
    host_query = await db.execute(
        select(Host).where(Host.project_id == project_id).where(Host.credential_id == secret.id)
    )
    target_hosts = host_query.scalars().all()
    if not target_hosts:
        return
    for trigger in triggers:
        playbook = await db.get(Playbook, trigger.playbook_id)
        if not playbook or playbook.project_id != project_id:
            continue
        filters = trigger.filters or {}
        if not _match_secret_filters(filters, secret):
            continue
        await _create_run_for_trigger(db, playbook, target_hosts, trigger.extra_vars or {}, "secret_rotated")
