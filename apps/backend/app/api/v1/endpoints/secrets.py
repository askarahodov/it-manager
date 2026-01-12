import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.secrets import SecretCreate, SecretRead, SecretReveal, SecretRevealInternal, SecretRotateRequest, SecretScope, SecretUpdate
from app.core.rbac import Permission
from app.db.models import Host, Secret
from app.services.audit import audit_log
from app.services.encryption import decrypt_value, encrypt_value
from app.services.triggers import dispatch_secret_triggers

router = APIRouter()
logger = logging.getLogger(__name__)


def _compute_next_rotation(last_rotated_at: datetime | None, interval_days: int | None) -> datetime | None:
    if not interval_days or interval_days <= 0:
        return None
    base = last_rotated_at or datetime.utcnow()
    return base + timedelta(days=interval_days)


@router.get("/", response_model=list[SecretRead])
async def list_secrets(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.secrets_read_metadata)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        select(Secret)
        .where(or_(Secret.project_id == project_id, Secret.project_id.is_(None)))
        .order_by(Secret.name)
    )
    return query.scalars().all()


@router.get("/{secret_id}", response_model=SecretRead)
async def get_secret(
    secret_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.secrets_read_metadata)),
    project_id: int = Depends(get_current_project_id),
):
    secret = await db.get(Secret, secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")
    if secret.project_id is not None and secret.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")
    return secret


@router.post("/", response_model=SecretRead, status_code=status.HTTP_201_CREATED)
async def create_secret(
    payload: SecretCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.secrets_write)),
    project_id: int = Depends(get_current_project_id),
):
    encrypted = encrypt_value(payload.value)
    encrypted_passphrase = encrypt_value(payload.passphrase) if payload.passphrase else None
    secret_project_id = None if payload.scope == SecretScope.global_ else project_id
    created_at = datetime.utcnow()
    last_rotated_at = created_at if payload.value else None
    next_rotated_at = _compute_next_rotation(last_rotated_at, payload.rotation_interval_days)
    secret = Secret(
        **payload.model_dump(exclude={"value", "passphrase"}),
        project_id=secret_project_id,
        encrypted_value=encrypted,
        encrypted_passphrase=encrypted_passphrase,
        last_rotated_at=last_rotated_at,
        next_rotated_at=next_rotated_at,
    )
    db.add(secret)
    await db.commit()
    await db.refresh(secret)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="secret.create",
        entity_type="secret",
        entity_id=secret.id,
        meta={"name": secret.name, "type": secret.type, "scope": secret.scope},
    )
    return secret


@router.put("/{secret_id}", response_model=SecretRead)
async def update_secret(
    secret_id: int,
    payload: SecretUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.secrets_write)),
    project_id: int = Depends(get_current_project_id),
):
    secret = await db.get(Secret, secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")
    if secret.project_id is not None and secret.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")

    should_trigger_rotation = payload.value is not None
    before = {
        "name": secret.name,
        "type": secret.type,
        "scope": secret.scope,
        "description": secret.description,
        "tags": secret.tags,
        "expires_at": secret.expires_at.isoformat() if secret.expires_at else None,
        "rotation_interval_days": secret.rotation_interval_days,
        "last_rotated_at": secret.last_rotated_at.isoformat() if secret.last_rotated_at else None,
        "next_rotated_at": secret.next_rotated_at.isoformat() if secret.next_rotated_at else None,
    }
    encrypted = encrypt_value(payload.value) if payload.value else secret.encrypted_value
    encrypted_passphrase = (
        encrypt_value(payload.passphrase) if payload.passphrase else secret.encrypted_passphrase
    )
    for field, value in payload.model_dump(exclude={"value", "passphrase"}, exclude_none=True).items():
        setattr(secret, field, value)
    if payload.scope == SecretScope.global_:
        secret.project_id = None
    else:
        secret.project_id = project_id
    secret.encrypted_value = encrypted
    secret.encrypted_passphrase = encrypted_passphrase
    if should_trigger_rotation:
        secret.last_rotated_at = datetime.utcnow()
    secret.next_rotated_at = _compute_next_rotation(secret.last_rotated_at, secret.rotation_interval_days)
    await db.commit()
    await db.refresh(secret)
    after = {
        "name": secret.name,
        "type": secret.type,
        "scope": secret.scope,
        "description": secret.description,
        "tags": secret.tags,
        "expires_at": secret.expires_at.isoformat() if secret.expires_at else None,
        "rotation_interval_days": secret.rotation_interval_days,
        "last_rotated_at": secret.last_rotated_at.isoformat() if secret.last_rotated_at else None,
        "next_rotated_at": secret.next_rotated_at.isoformat() if secret.next_rotated_at else None,
    }
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="secret.update",
        entity_type="secret",
        entity_id=secret.id,
        meta={"name": secret.name, "type": secret.type, "scope": secret.scope, "before": before, "after": after},
    )
    if should_trigger_rotation:
        await dispatch_secret_triggers(db, secret, project_id)
    return secret


@router.post("/{secret_id}/rotate", response_model=SecretRead)
async def rotate_secret(
    secret_id: int,
    payload: SecretRotateRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.secrets_write)),
    project_id: int = Depends(get_current_project_id),
):
    secret = await db.get(Secret, secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")
    if secret.project_id is not None and secret.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")

    secret.encrypted_value = encrypt_value(payload.value)
    secret.encrypted_passphrase = encrypt_value(payload.passphrase) if payload.passphrase else None
    secret.last_rotated_at = datetime.utcnow()
    secret.next_rotated_at = _compute_next_rotation(secret.last_rotated_at, secret.rotation_interval_days)
    await db.commit()
    await db.refresh(secret)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="secret.rotate",
        entity_type="secret",
        entity_id=secret.id,
        meta={"name": secret.name, "type": secret.type, "scope": secret.scope},
    )
    await notify_event(
        db,
        project_id=project_id,
        event="secret.rotated",
        payload={"secret_id": secret.id, "name": secret.name},
    )
    await dispatch_secret_triggers(db, secret, project_id)
    return secret


@router.post("/{secret_id}/reveal", response_model=SecretReveal)
async def reveal_secret(
    secret_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.secrets_reveal)),
    project_id: int = Depends(get_current_project_id),
):
    secret = await db.get(Secret, secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")
    if secret.project_id is not None and secret.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")

    value = decrypt_value(secret.encrypted_value)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="secret.reveal",
        entity_type="secret",
        entity_id=secret.id,
        meta={"name": secret.name, "type": secret.type},
    )
    return SecretReveal(value=value)


@router.post("/{secret_id}/reveal-internal", response_model=SecretRevealInternal)
async def reveal_secret_internal(
    secret_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.secrets_reveal)),
    project_id: int = Depends(get_current_project_id),
):
    """Раскрытие секрета для воркера/автоматизации (admin-only).

    Возвращает passphrase для private_key (если есть).
    """
    secret = await db.get(Secret, secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")
    if secret.project_id is not None and secret.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")

    value = decrypt_value(secret.encrypted_value)
    passphrase = decrypt_value(secret.encrypted_passphrase) if secret.encrypted_passphrase else None
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="secret.reveal_internal",
        entity_type="secret",
        entity_id=secret.id,
        meta={"name": secret.name, "type": secret.type},
    )
    return SecretRevealInternal(value=value, passphrase=passphrase)


@router.delete("/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    secret_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.secrets_write)),
    project_id: int = Depends(get_current_project_id),
):
    secret = await db.get(Secret, secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")
    if secret.project_id is not None and secret.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Секрет не найден")

    host_query = select(Host).where(Host.credential_id == secret_id)
    if secret.project_id is not None:
        host_query = host_query.where(Host.project_id == project_id)
    used_by = await db.execute(
        host_query
    )
    if used_by.scalar():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Секрет привязан к хосту, удалите связь перед удалением секрета",
        )
    try:
        await db.delete(secret)
        await db.commit()
        await audit_log(
            db,
            project_id=project_id,
            actor=principal.email,
            actor_role=str(principal.role.value),
            action="secret.delete",
            entity_type="secret",
            entity_id=secret_id,
            meta={"name": secret.name, "type": secret.type, "scope": secret.scope},
        )
    except IntegrityError as exc:
        await db.rollback()
        logger.error("Ошибка целостности при удалении секрета %s: %s", secret_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Удаление невозможно из-за связей",
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("Не удалось удалить секрет %s", secret_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось удалить секрет",
        ) from exc
    return None
