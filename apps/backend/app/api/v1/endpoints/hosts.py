import asyncio
import logging
import subprocess
from datetime import datetime
import json
from typing import Optional

import asyncssh
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.hosts import HostCreate, HostRead, HostStatusCheckResponse, HostUpdate
from app.core.rbac import Permission, has_permission
from app.db.models import Host, HostCheckMethod, HostStatus, Secret, SecretType, User
from app.services.access import apply_host_scope, host_access_clause
from app.services.audit import audit_log
from app.services.encryption import decrypt_value
from app.services.projects import ProjectAccessDenied, ProjectNotFound, resolve_current_project_id

router = APIRouter()
logger = logging.getLogger(__name__)


async def _probe_ping(host: Host) -> HostStatus:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            "1",
            "-W",
            "1",
            host.hostname,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await proc.wait()
        return HostStatus.online if rc == 0 else HostStatus.offline
    except FileNotFoundError:
        logger.warning("ping не установлен в контейнере backend; fallback на tcp")
        return await _probe_tcp(host)
    except Exception:
        return HostStatus.offline


async def _probe_tcp(host: Host) -> HostStatus:
    try:
        reader, writer = await asyncio.open_connection(host.hostname, host.port)
        writer.close()
        await writer.wait_closed()
        return HostStatus.online
    except asyncio.TimeoutError:
        return HostStatus.offline
    except Exception:
        return HostStatus.offline


async def _probe_ssh(host: Host) -> HostStatus:
    """Проверка SSH connect (без interactive PTY). Требует credential для password/ключа."""
    password: Optional[str] = None
    private_key: Optional[str] = None
    passphrase: Optional[str] = None

    if host.credential:
        try:
            decrypted = decrypt_value(host.credential.encrypted_value)
            if host.credential.type == SecretType.password:
                password = decrypted
            elif host.credential.type == SecretType.private_key:
                private_key = decrypted
                if host.credential.encrypted_passphrase:
                    passphrase = decrypt_value(host.credential.encrypted_passphrase)
        except Exception:
            return HostStatus.offline

    try:
        conn = await asyncssh.connect(
            host.hostname,
            port=host.port,
            username=host.username,
            password=password,
            client_keys=[private_key] if private_key else None,
            passphrase=passphrase,
            known_hosts=None,
            server_host_key_algs=["ssh-ed25519", "ssh-rsa"],
        )
        conn.close()
        await conn.wait_closed()
        return HostStatus.online
    except Exception:
        return HostStatus.offline


@router.get("/", response_model=list[HostRead])
async def list_hosts(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
    search: Optional[str] = Query(default=None, description="Поиск по name/hostname (ILIKE)"),
    status_filter: Optional[HostStatus] = Query(default=None, alias="status", description="Фильтр по статусу"),
    environment: Optional[str] = Query(default=None, description="Фильтр по environment"),
    os_type: Optional[str] = Query(default=None, description="Фильтр по os_type"),
    tag_key: Optional[str] = Query(default=None, description="Фильтр по tags.<key>"),
    tag_value: Optional[str] = Query(default=None, description="Значение для tag_key"),
    sort_by: str = Query(default="name", description="Поле сортировки: name|hostname|status|environment|os_type|id"),
    sort_dir: str = Query(default="asc", description="asc|desc"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Host)
    stmt = stmt.where(Host.project_id == project_id)
    stmt = apply_host_scope(stmt, principal)

    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(or_(Host.name.ilike(q), Host.hostname.ilike(q)))
    if status_filter:
        stmt = stmt.where(Host.status == status_filter)
    if environment:
        stmt = stmt.where(Host.environment == environment)
    if os_type:
        stmt = stmt.where(Host.os_type == os_type)
    if tag_key and tag_value is not None:
        # JSONB tags: {"env":"prod"} => tags->>'env' = 'prod'
        stmt = stmt.where(Host.tags[tag_key].astext == tag_value)

    sort_map = {
        "id": Host.id,
        "name": Host.name,
        "hostname": Host.hostname,
        "status": Host.status,
        "environment": Host.environment,
        "os_type": Host.os_type,
    }
    sort_col = sort_map.get(sort_by, Host.name)
    order_fn = desc if sort_dir.lower() == "desc" else asc
    stmt = stmt.order_by(order_fn(sort_col)).limit(limit).offset(offset)

    query = await db.execute(stmt)
    hosts = query.scalars().all()
    return hosts


@router.post("/", response_model=HostRead, status_code=status.HTTP_201_CREATED)
async def create_host(
    payload: HostCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    if payload.credential_id:
        secret = await db.get(Secret, int(payload.credential_id))
        if not secret or secret.project_id != project_id:
            raise HTTPException(status_code=400, detail="Credential должен быть из текущего проекта")

    new_host = Host(**payload.model_dump(), project_id=project_id)
    db.add(new_host)
    await db.commit()
    await db.refresh(new_host)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.create",
        entity_type="host",
        entity_id=new_host.id,
        meta={"name": new_host.name, "hostname": new_host.hostname, "port": new_host.port},
    )
    return new_host


@router.get("/{host_id}", response_model=HostRead)
async def get_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host).where(Host.id == host_id).where(Host.project_id == project_id).where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")
    return host


@router.put("/{host_id}", response_model=HostRead)
async def update_host(
    host_id: int,
    payload: HostUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host).where(Host.id == host_id).where(Host.project_id == project_id).where(host_access_clause(principal))
    )
    existing = res.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")

    updates = payload.model_dump(exclude_unset=True)
    if "credential_id" in updates and updates["credential_id"]:
        secret = await db.get(Secret, int(updates["credential_id"]))
        if not secret or secret.project_id != project_id:
            raise HTTPException(status_code=400, detail="Credential должен быть из текущего проекта")

    for field, value in updates.items():
        setattr(existing, field, value)
    await db.commit()
    await db.refresh(existing)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.update",
        entity_type="host",
        entity_id=existing.id,
        meta={"name": existing.name, "hostname": existing.hostname, "port": existing.port},
    )
    return existing


@router.delete("/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host).where(Host.id == host_id).where(Host.project_id == project_id).where(host_access_clause(principal))
    )
    existing = res.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")
    await db.delete(existing)
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.delete",
        entity_type="host",
        entity_id=host_id,
        meta={"name": existing.name, "hostname": existing.hostname},
    )
    return None


@router.post("/{host_id}/status-check", response_model=HostStatusCheckResponse)
async def check_status(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_check)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host).where(Host.id == host_id).where(Host.project_id == project_id).where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")

    method = host.check_method or HostCheckMethod.tcp
    if method == HostCheckMethod.ping:
        status_result = await _probe_ping(host)
    elif method == HostCheckMethod.ssh:
        status_result = await _probe_ssh(host)
    else:
        status_result = await _probe_tcp(host)
    host.status = status_result
    host.last_checked_at = datetime.utcnow()
    await db.commit()
    await db.refresh(host)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.status_check",
        entity_type="host",
        entity_id=host.id,
        meta={"status": host.status, "method": str(method.value)},
    )
    return host


@router.websocket("/{host_id}/terminal")
async def host_terminal(
    websocket: WebSocket,
    host_id: int,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket -> SSH (PTY) терминал.

    Протокол сообщений:
    - по умолчанию: текстовые данные (как есть) — отправляются в stdin SSH процесса
    - опционально: JSON-команды
      - {"type":"resize","cols":123,"rows":45}
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    from app.core.security import verify_token

    try:
        payload = verify_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    role = payload.get("role", "user")
    if not has_permission(role, Permission.hosts_ssh):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    subject = payload.get("sub")
    if not subject:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    qp_project_id = websocket.query_params.get("project_id")
    if qp_project_id:
        try:
            requested_project_id = int(qp_project_id)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    else:
        requested_project_id = None

    res = await db.execute(select(User).where(User.email == str(subject)))
    principal = res.scalar_one_or_none()
    if not principal:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        current_project_id = await resolve_current_project_id(db, principal, requested_project_id)
    except (ProjectNotFound, ProjectAccessDenied):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    res = await db.execute(
        select(Host)
        .where(Host.id == host_id)
        .where(Host.project_id == current_project_id)
        .where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("WS terminal start host_id=%s user=%s", host_id, payload.get("sub"))
    await audit_log(
        db,
        project_id=current_project_id,
        actor=payload.get("sub"),
        actor_role=payload.get("role"),
        action="ssh.connect",
        entity_type="host",
        entity_id=host_id,
        meta={"hostname": host.hostname, "port": host.port, "username": host.username},
    )
    password: Optional[str] = None
    private_key: Optional[str] = None
    passphrase: Optional[str] = None

    if host.credential:
        try:
            decrypted = decrypt_value(host.credential.encrypted_value)
            if host.credential.type == SecretType.password:
                password = decrypted
            elif host.credential.type == SecretType.private_key:
                private_key = decrypted
                if host.credential.encrypted_passphrase:
                    passphrase = decrypt_value(host.credential.encrypted_passphrase)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Не удалось расшифровать credential для host_id=%s: %s", host_id, exc)
            await websocket.send_text("Ошибка: не удалось расшифровать секрет для подключения.\n")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return

    try:
        conn = await asyncssh.connect(
            host.hostname,
            port=host.port,
            username=host.username,
            password=password,
            client_keys=[asyncssh.import_private_key(private_key, passphrase=passphrase)] if private_key else None,
            known_hosts=None,
            connect_timeout=10,
            keepalive_interval=30,
            keepalive_count_max=3,
            encoding=None,
        )
    except Exception as exc:
        logger.exception("SSH connect error host_id=%s: %s", host_id, exc)
        await websocket.send_text(f"SSH ошибка: {exc}\n")
        await audit_log(
            db,
            project_id=current_project_id,
            actor=payload.get("sub"),
            actor_role=payload.get("role"),
            action="ssh.connect_failed",
            entity_type="host",
            entity_id=host_id,
            success=False,
            meta={"error": str(exc)},
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    try:
        process = await conn.create_process(term_type="xterm-256color", term_size=(80, 24))
        process.stdin.write(b"\n")
        await process.stdin.drain()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось открыть shell host_id=%s: %s", host_id, exc)
        await websocket.send_text(f"Не удалось открыть shell: {exc}\n")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        conn.close()
        return

    async def _forward_stream(stream):
        try:
            while True:
                data = await stream.read(1024)
                if not data:
                    break
                # encoding=None => bytes
                if isinstance(data, (bytes, bytearray)):
                    await websocket.send_text(bytes(data).decode(errors="ignore"))
                else:
                    await websocket.send_text(str(data))
        except Exception as exc:  # noqa: BLE001
            logger.debug("stdout/stderr stream closed: %s", exc)

    async def _forward_ws():
        try:
            async for message in websocket.iter_text():
                if message and message[0] == "{":
                    try:
                        obj = json.loads(message)
                    except Exception:
                        obj = None
                    if isinstance(obj, dict):
                        message_type = obj.get("type")
                        if message_type == "resize":
                            cols = int(obj.get("cols", 80))
                            rows = int(obj.get("rows", 24))
                            cols = max(20, min(cols, 500))
                            rows = max(5, min(rows, 200))
                            process.change_terminal_size(cols, rows)
                            continue
                # обычные данные терминала
                data = message.encode("utf-8", errors="ignore")
                process.stdin.write(data)
                await process.stdin.drain()
        except WebSocketDisconnect:
            logger.info("WS закрыт клиентом host_id=%s", host_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка чтения WS host_id=%s: %s", host_id, exc)

    stdout_task = asyncio.create_task(_forward_stream(process.stdout))
    stderr_task = asyncio.create_task(_forward_stream(process.stderr))
    ws_task = asyncio.create_task(_forward_ws())
    exit_task = asyncio.create_task(process.wait())

    # Держим сессию пока клиент не закроет WS или пока не завершится shell.
    done, pending = await asyncio.wait({ws_task, exit_task}, return_when=asyncio.FIRST_COMPLETED)

    for task in (stdout_task, stderr_task, ws_task, exit_task):
        if task not in done:
            task.cancel()

    try:
        process.stdin.write_eof()
    except Exception:
        pass
    try:
        process.kill()
        await process.wait()
    except Exception:
        pass
    conn.close()
    await audit_log(
        db,
        project_id=current_project_id,
        actor=payload.get("sub"),
        actor_role=payload.get("role"),
        action="ssh.disconnect",
        entity_type="host",
        entity_id=host_id,
        meta={"hostname": host.hostname, "port": host.port},
    )
