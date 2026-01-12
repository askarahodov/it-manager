import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.approvals import ApprovalDecisionRequest, ApprovalRead
from app.core.rbac import Permission
from app.db.models import ApprovalRequest, ApprovalStatus, JobRun
from app.services.audit import audit_log
from app.services.notifications import notify_event
from app.services.queue import enqueue_run

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_admin(principal) -> None:
    if getattr(principal.role, "value", str(principal.role)) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


@router.get("/", response_model=list[ApprovalRead])
async def list_approvals(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.project_id == project_id).order_by(ApprovalRequest.created_at.desc())
    )
    return query.scalars().all()


@router.post("/{approval_id}/decision", status_code=status.HTTP_204_NO_CONTENT)
async def decide_approval(
    approval_id: int,
    payload: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(principal)
    approval = await db.get(ApprovalRequest, approval_id)
    if not approval or approval.project_id != project_id:
        raise HTTPException(status_code=404, detail="Approval не найден")
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(status_code=409, detail="Approval уже обработан")

    approval.status = ApprovalStatus.approved if payload.status == "approved" else ApprovalStatus.rejected
    approval.reason = payload.reason
    approval.decided_by = principal.id
    approval.decided_at = datetime.utcnow()

    run = await db.get(JobRun, approval.run_id)
    if not run or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Run не найден")
    run.target_snapshot = run.target_snapshot or {}
    run.target_snapshot["approval_status"] = approval.status.value
    run.target_snapshot["approval_id"] = approval.id
    await db.commit()

    if approval.status == ApprovalStatus.approved:
        await enqueue_run(run.id, project_id=project_id)
        await audit_log(
            db,
            project_id=project_id,
            actor=principal.email,
            actor_role=str(principal.role.value),
            action="approval.approve",
            entity_type="approval",
            entity_id=approval.id,
            meta={"run_id": run.id},
        )
        await notify_event(
            db,
            project_id=project_id,
            event="approval.approved",
            payload={"approval_id": approval.id, "run_id": run.id},
        )
    else:
        await audit_log(
            db,
            project_id=project_id,
            actor=principal.email,
            actor_role=str(principal.role.value),
            action="approval.reject",
            entity_type="approval",
            entity_id=approval.id,
            meta={"run_id": run.id, "reason": payload.reason},
        )
        await notify_event(
            db,
            project_id=project_id,
            event="approval.rejected",
            payload={"approval_id": approval.id, "run_id": run.id, "reason": payload.reason},
        )

    return None
