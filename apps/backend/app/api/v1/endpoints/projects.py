import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db, require_permission
from app.api.v1.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
from app.core.rbac import Permission
from app.db.models import Project
from app.services.audit import audit_log
from app.services.access import is_project_allowed

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db), principal=Depends(require_permission(Permission.projects_read))):
    q = await db.execute(select(Project).order_by(Project.name))
    projects = q.scalars().all()
    return [p for p in projects if is_project_allowed(principal, p.id)]


@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.projects_write)),
):
    project = Project(name=payload.name.strip(), description=payload.description)
    db.add(project)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Проект с таким именем уже существует")
    await db.refresh(project)
    await audit_log(
        db,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="project.create",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        meta={"name": project.name},
    )
    return project


@router.put("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.projects_write)),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            setattr(project, k, v)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Проект с таким именем уже существует")
    await db.refresh(project)
    await audit_log(
        db,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="project.update",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        meta={"name": project.name},
    )
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.projects_write)),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if project.name == "default":
        raise HTTPException(status_code=400, detail="Нельзя удалить проект default")
    await db.delete(project)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.error("Cannot delete project %s: %s", project_id, exc)
        raise HTTPException(status_code=400, detail="Нельзя удалить проект: есть связанные сущности")
    await audit_log(
        db,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="project.delete",
        entity_type="project",
        entity_id=project_id,
        project_id=project_id,
        meta={"name": project.name},
    )
    return None
