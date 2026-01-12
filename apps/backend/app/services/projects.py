from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project, User
from app.services.access import is_project_allowed


class ProjectResolutionError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ProjectNotFound(ProjectResolutionError):
    project_id: int


@dataclass(frozen=True, slots=True)
class ProjectAccessDenied(ProjectResolutionError):
    project_id: int | None = None


def _normalize_int_list(value) -> list[int]:
    if not isinstance(value, list):
        return []
    return [int(x) for x in value if str(x).isdigit()]


async def resolve_current_project_id(
    db: AsyncSession,
    principal: User,
    requested_project_id: int | None,
    *,
    default_project_name: str = "default",
) -> int:
    """Определяет текущий проект (tenant) для запроса.

    Правила:
    - если проект явно задан (requested_project_id) — проверяем существование и доступ;
    - если у пользователя задан allowlist (allowed_project_ids) — выбираем default только если он разрешён,
      иначе первый доступный project_id из allowlist;
    - иначе используем default проект или первый существующий; если проектов нет — fallback на 1.
    """

    if requested_project_id is not None:
        project = await db.get(Project, int(requested_project_id))
        if not project:
            raise ProjectNotFound(project_id=int(requested_project_id))
        if not is_project_allowed(principal, project.id):
            raise ProjectAccessDenied(project_id=project.id)
        return int(project.id)

    allowed = principal.allowed_project_ids
    if allowed is not None:
        ids = _normalize_int_list(allowed)
        if not ids:
            raise ProjectAccessDenied(project_id=None)

        res = await db.execute(select(Project.id).where(Project.name == default_project_name).limit(1))
        default_id = res.scalar_one_or_none()
        if default_id is not None and int(default_id) in ids:
            return int(default_id)

        res = await db.execute(select(Project.id).where(Project.id.in_(ids)).order_by(Project.id.asc()).limit(1))
        pid = res.scalar_one_or_none()
        if pid is None:
            raise ProjectAccessDenied(project_id=None)
        return int(pid)

    res = await db.execute(select(Project.id).where(Project.name == default_project_name).limit(1))
    pid = res.scalar_one_or_none()
    if pid is not None:
        if not is_project_allowed(principal, int(pid)):
            raise ProjectAccessDenied(project_id=int(pid))
        return int(pid)

    res = await db.execute(select(Project.id).order_by(Project.id.asc()).limit(1))
    pid = res.scalar_one_or_none()
    if pid is not None:
        if not is_project_allowed(principal, int(pid)):
            raise ProjectAccessDenied(project_id=int(pid))
        return int(pid)

    if not is_project_allowed(principal, 1):
        raise ProjectAccessDenied(project_id=1)
    return 1

