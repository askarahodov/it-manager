from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db, require_permission
from app.api.v1.schemas.admin_settings import GlobalSettings, GlobalSettingsPublic, GlobalSettingsUpdate
from app.core.rbac import Permission
from app.db.models import GlobalSetting
from app.services.audit import audit_log

router = APIRouter()


def _require_admin(principal) -> None:
    if getattr(principal.role, "value", str(principal.role)) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


DEFAULT_SETTINGS = GlobalSettings()


async def _load_settings(db: AsyncSession) -> GlobalSettings:
    rows = await db.execute(select(GlobalSetting))
    items = {row.key: row.value for row in rows.scalars().all()}
    data = DEFAULT_SETTINGS.model_dump()
    for key, value in items.items():
        if key in data:
            data[key] = value
    return GlobalSettings(**data)


@router.get("/", response_model=GlobalSettings)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.projects_read)),
):
    _require_admin(principal)
    return await _load_settings(db)


@router.get("/public", response_model=GlobalSettingsPublic)
async def get_public_settings(
    db: AsyncSession = Depends(get_db),
):
    settings = await _load_settings(db)
    return GlobalSettingsPublic(
        maintenance_mode=settings.maintenance_mode,
        banner_message=settings.banner_message,
        banner_level=settings.banner_level,
    )


@router.put("/", response_model=GlobalSettings)
async def update_settings(
    payload: GlobalSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.projects_write)),
):
    _require_admin(principal)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        row = await db.get(GlobalSetting, key)
        if not row:
            row = GlobalSetting(key=key, value=value)
            db.add(row)
        else:
            row.value = value
    await db.commit()
    current = await _load_settings(db)
    await audit_log(
        db,
        project_id=None,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="global_settings.update",
        entity_type="global_settings",
        entity_id=None,
        meta={"updated_keys": list(updates.keys())},
    )
    return current
