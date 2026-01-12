from typing import AsyncGenerator, Dict, Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Permission, has_any_permission, has_permission
from app.core.security import verify_token
from app.db import async_session
from app.db.models import User
from app.services.projects import ProjectAccessDenied, ProjectNotFound, resolve_current_project_id

security_scheme = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> Dict[str, str]:
    try:
        payload = verify_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учетные данные",
        ) from exc
    return {"sub": payload.get("sub"), "role": payload.get("role", "user")}


async def get_current_principal(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> User:
    """Текущий пользователь из БД.

    Используется для RBAC2.0 (роли/пермишены) и ограничений доступа по окружениям/группам.
    """
    try:
        payload = verify_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учетные данные",
        ) from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен без subject")

    res = await db.execute(select(User).where(User.email == str(subject)))
    principal = res.scalar_one_or_none()
    if not principal:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return principal


def require_permission(permission: Permission):
    def _dependency(principal: User = Depends(get_current_principal)) -> User:
        if not has_permission(getattr(principal.role, "value", str(principal.role)), permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return principal

    return _dependency


def require_any_permission(*permissions: Permission):
    def _dependency(principal: User = Depends(get_current_principal)) -> User:
        role_value = getattr(principal.role, "value", str(principal.role))
        if not has_any_permission(role_value, permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return principal

    return _dependency


async def get_current_project_id(
    db: AsyncSession = Depends(get_db),
    principal: User = Depends(get_current_principal),
    x_project_id: Optional[int] = Header(default=None, alias="X-Project-Id"),
) -> int:
    """Текущий проект (tenant).

    Правила (MVP):
    - если `X-Project-Id` не передан — используем `default` (если доступен) или первый доступный проект;
    - если передан, но проекта нет — 404.
    """

    try:
        return await resolve_current_project_id(db, principal, int(x_project_id) if x_project_id is not None else None)
    except ProjectNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    except ProjectAccessDenied:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к проекту")
