import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_db
from app.api.v1.schemas.users import UserCreate, UserRead, UserUpdate
from app.core.hash import get_password_hash
from app.db.models import User, UserRole
from app.services.audit import audit_log

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


async def _admin_count(db: AsyncSession) -> int:
    res = await db.execute(select(func.count()).select_from(User).where(User.role == UserRole.admin))
    return int(res.scalar_one())


@router.get("/", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    _require_admin(user)
    res = await db.execute(select(User).order_by(User.id.asc()))
    return res.scalars().all()


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    _require_admin(user)
    email = payload.email.strip().lower()
    new_user = User(
        email=email,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        allowed_environments=payload.allowed_environments,
        allowed_group_ids=payload.allowed_group_ids,
        allowed_project_ids=payload.allowed_project_ids,
    )
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    await db.refresh(new_user)
    await audit_log(
        db,
        actor=user.get("sub"),
        actor_role=user.get("role"),
        action="user.create",
        entity_type="user",
        entity_id=new_user.id,
        meta={"email": new_user.email, "role": str(new_user.role.value)},
    )
    return new_user


@router.put("/{user_id}", response_model=UserRead)
async def update_user(user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    _require_admin(user)
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if payload.role is not None and target.role == UserRole.admin and payload.role != UserRole.admin:
        if await _admin_count(db) <= 1:
            raise HTTPException(status_code=400, detail="Нельзя снять роль admin с последнего администратора")

    if payload.email is not None:
        target.email = payload.email.strip().lower()
    if payload.role is not None:
        target.role = payload.role
    if payload.password is not None:
        target.password_hash = get_password_hash(payload.password)
    if payload.allowed_environments is not None:
        target.allowed_environments = payload.allowed_environments
    if payload.allowed_group_ids is not None:
        target.allowed_group_ids = payload.allowed_group_ids
    if payload.allowed_project_ids is not None:
        target.allowed_project_ids = payload.allowed_project_ids

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    await db.refresh(target)
    await audit_log(
        db,
        actor=user.get("sub"),
        actor_role=user.get("role"),
        action="user.update",
        entity_type="user",
        entity_id=target.id,
        meta={"email": target.email, "role": str(target.role.value)},
    )
    return target


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    _require_admin(user)
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target.role == UserRole.admin:
        if await _admin_count(db) <= 1:
            raise HTTPException(status_code=400, detail="Нельзя удалить последнего администратора")
    await db.delete(target)
    await db.commit()
    await audit_log(
        db,
        actor=user.get("sub"),
        actor_role=user.get("role"),
        action="user.delete",
        entity_type="user",
        entity_id=user_id,
        meta={"email": target.email},
    )
    return None
