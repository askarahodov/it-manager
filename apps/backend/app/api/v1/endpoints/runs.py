import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_current_user, get_db, require_permission
from app.api.v1.schemas.runs import (
    RunAppendLogRequest,
    RunClaimResponse,
    RunRead,
    RunSetStatusRequest,
)
from app.core.rbac import Permission, has_permission
from app.core.security import verify_token
from app.core.config import settings
from app.db.models import JobRun, JobStatus, Playbook, User
from app.services.audit import audit_log
from app.services.projects import ProjectAccessDenied, ProjectNotFound, resolve_current_project_id

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


@router.get("/", response_model=list[RunRead])
async def list_runs(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(select(JobRun).where(JobRun.project_id == project_id).order_by(JobRun.created_at.desc()))
    return query.scalars().all()


@router.get("/{run_id}", response_model=RunRead)
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    run = await db.get(JobRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    if run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return run


@router.post("/{run_id}/claim", response_model=RunClaimResponse)
async def claim_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    """Выдаёт воркеру спецификацию запуска и переводит JobRun в running."""
    _require_admin(user)
    run = await db.get(JobRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    if run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    if run.status != JobStatus.pending:
        raise HTTPException(status_code=409, detail="Запуск уже взят в работу или завершён")

    playbook = await db.get(Playbook, run.playbook_id)
    if not playbook:
        raise HTTPException(status_code=500, detail="Плейбук отсутствует")
    if playbook.project_id != project_id:
        raise HTTPException(status_code=500, detail="Плейбук из другого проекта")

    run.status = JobStatus.running
    run.started_at = datetime.utcnow()
    await db.commit()
    await db.refresh(run)
    await audit_log(
        db,
        project_id=project_id,
        actor=user.get("sub"),
        actor_role=user.get("role"),
        action="run.claim",
        entity_type="run",
        entity_id=run.id,
        meta={"playbook_id": run.playbook_id},
    )

    return RunClaimResponse(
        run=run,
        playbook={
            "id": playbook.id,
            "name": playbook.name,
            "stored_content": playbook.stored_content,
            "repo_path": playbook.repo_path,
            "variables": playbook.variables or {},
        },
    )


@router.post("/{run_id}/append-log", status_code=status.HTTP_204_NO_CONTENT)
async def append_log(
    run_id: int,
    payload: RunAppendLogRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(user)
    run = await db.get(JobRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    if run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    # Простой append (MVP). Для больших логов заменим на отдельное хранилище.
    run.logs = (run.logs or "") + payload.chunk
    await db.commit()
    return None


@router.post("/{run_id}/set-status", status_code=status.HTTP_204_NO_CONTENT)
async def set_status(
    run_id: int,
    payload: RunSetStatusRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(user)
    run = await db.get(JobRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    if run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    run.status = payload.status
    if payload.finished_at:
        run.finished_at = payload.finished_at
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=user.get("sub"),
        actor_role=user.get("role"),
        action="run.set_status",
        entity_type="run",
        entity_id=run.id,
        meta={"status": run.status},
    )
    return None


async def _get_user_from_query_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    try:
        payload = verify_token(token)
    except Exception:
        return None
    return {"sub": payload.get("sub"), "role": payload.get("role", "user")}

async def _get_principal_from_subject(db: AsyncSession, subject: str) -> Optional[User]:
    res = await db.execute(select(User).where(User.email == str(subject)).limit(1))
    return res.scalar_one_or_none()


@router.get("/{run_id}/stream")
async def stream_logs(run_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """SSE stream логов для UI.

    EventSource не умеет заголовки Authorization, поэтому принимаем token в query.
    """
    token = request.query_params.get("token")
    user = await _get_user_from_query_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Нужен токен")
    if not has_permission(user.get("role"), Permission.ansible_read):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    try:
        qp_project_id = request.query_params.get("project_id")
        requested_project_id = int(qp_project_id) if qp_project_id else None
    except Exception:
        raise HTTPException(status_code=400, detail="project_id некорректный")

    subject = user.get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail="Нужен токен")

    principal = await _get_principal_from_subject(db, str(subject))
    if not principal:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    try:
        project_id = await resolve_current_project_id(db, principal, requested_project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="Проект не найден")
    except ProjectAccessDenied:
        raise HTTPException(status_code=403, detail="Нет доступа к проекту")

    async def event_gen() -> AsyncGenerator[bytes, None]:
        offset = 0
        while True:
            if await request.is_disconnected():
                break

            run = await db.get(JobRun, run_id)
            if not run:
                yield b"event: error\ndata: run-not-found\n\n"
                break
            if run.project_id != project_id:
                yield b"event: error\ndata: run-not-found\n\n"
                break

            text = run.logs or ""
            if offset < len(text):
                chunk = text[offset:]
                offset = len(text)
                # data: ... \n\n (разбиваем, чтобы не ломать SSE)
                for line in chunk.splitlines(True):
                    payload = line.replace("\r", "\\r").replace("\n", "\\n")
                    yield f"data: {payload}\n\n".encode("utf-8")

            if run.status in {JobStatus.success, JobStatus.failed}:
                yield f"event: done\ndata: {run.status}\n\n".encode("utf-8")
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _safe_artifact_path(run_id: int, name: str) -> Path:
    allowed = {"run.log", "playbook.yml", "inventory.public.ini"}
    if name not in allowed:
        raise HTTPException(status_code=404, detail="Артефакт не найден")
    base = Path(settings.artifacts_dir) / "runs" / str(run_id)
    return base / name


@router.get("/{run_id}/artifacts", response_model=list[dict])
async def list_artifacts(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(user)
    run = await db.get(JobRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    if run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    base = Path(settings.artifacts_dir) / "runs" / str(run_id)
    if not base.exists():
        return []
    items: list[dict] = []
    for name in ["run.log", "playbook.yml", "inventory.public.ini"]:
        p = base / name
        if not p.exists() or not p.is_file():
            continue
        st = p.stat()
        items.append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime)})
    return items


@router.get("/{run_id}/artifacts/{name}")
async def download_artifact(run_id: int, name: str, request: Request, db: AsyncSession = Depends(get_db)):
    token = request.query_params.get("token")
    user = await _get_user_from_query_token(token)
    if not user:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            try:
                payload = verify_token(auth.split(" ", 1)[1].strip())
                user = {"sub": payload.get("sub"), "role": payload.get("role", "user")}
            except Exception:
                user = None
    if not user:
        raise HTTPException(status_code=401, detail="Нужен токен")
    _require_admin(user)

    try:
        qp_project_id = request.query_params.get("project_id")
        requested_project_id = int(qp_project_id) if qp_project_id else None
    except Exception:
        raise HTTPException(status_code=400, detail="project_id некорректный")

    subject = user.get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail="Нужен токен")

    principal = await _get_principal_from_subject(db, str(subject))
    if not principal:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    try:
        project_id = await resolve_current_project_id(db, principal, requested_project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="Проект не найден")
    except ProjectAccessDenied:
        raise HTTPException(status_code=403, detail="Нет доступа к проекту")

    run = await db.get(JobRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    if run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    path = _safe_artifact_path(run_id, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Артефакт не найден")
    return FileResponse(path=str(path), filename=name)
