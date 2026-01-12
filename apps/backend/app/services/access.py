"""Ограничения доступа к сущностям по окружениям и группам (RBAC2.0).

MVP: ограничения задаются в users.allowed_environments / users.allowed_group_ids.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import Select, and_, literal, select

from app.db.models import DynamicGroupHostCache, GroupHost, Host, HostGroup, User


def _normalize_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return []


def host_access_clause(principal: User):
    """SQLA-условие для доступа к host.

    Правила:
    - allowed_environments=None => доступ ко всем env
    - allowed_group_ids=None => доступ ко всем группам
    - пустой список => нет доступа
    """

    clauses = []
    allowed_envs = principal.allowed_environments
    allowed_groups = principal.allowed_group_ids

    if allowed_envs is not None:
        envs = [str(x) for x in _normalize_list(allowed_envs)]
        if not envs:
            return literal(False)
        clauses.append(Host.environment.in_(envs))

    if allowed_groups is not None:
        group_ids = [int(x) for x in _normalize_list(allowed_groups) if str(x).isdigit()]
        if not group_ids:
            return literal(False)

        static_hosts = select(GroupHost.host_id).where(GroupHost.group_id.in_(group_ids))
        dynamic_hosts = select(DynamicGroupHostCache.host_id).where(DynamicGroupHostCache.group_id.in_(group_ids))
        host_ids = static_hosts.union(dynamic_hosts)
        clauses.append(Host.id.in_(host_ids))

    if not clauses:
        return literal(True)
    return and_(*clauses)


def apply_host_scope(stmt: Select, principal: User) -> Select:
    """Применяет ограничения доступа к выборке hosts."""
    return stmt.where(host_access_clause(principal))


def is_project_allowed(principal: User, project_id: int) -> bool:
    """Проверка доступа пользователя к проекту.

    Правила:
    - allowed_project_ids=None => доступны все проекты
    - [] => нет доступа
    """
    allowed = principal.allowed_project_ids
    if allowed is None:
        return True
    ids = [int(x) for x in _normalize_list(allowed) if str(x).isdigit()]
    return int(project_id) in ids


def project_access_clause(principal: User, project_id_col):
    """SQLA-условие для проектного скоупа.

    Применяется к таблицам с колонкой project_id.
    """
    allowed = principal.allowed_project_ids
    if allowed is None:
        return literal(True)
    ids = [int(x) for x in _normalize_list(allowed) if str(x).isdigit()]
    if not ids:
        return literal(False)
    return project_id_col.in_(ids)


def group_access_clause(principal: User):
    """SQLA-условие для доступа к группе.

    Пока используем allowed_group_ids как список доступных group_id.
    None => доступны все группы.
    """
    allowed_groups = principal.allowed_group_ids
    if allowed_groups is None:
        return literal(True)
    group_ids = [int(x) for x in _normalize_list(allowed_groups) if str(x).isdigit()]
    if not group_ids:
        return literal(False)
    return HostGroup.id.in_(group_ids)


def apply_group_scope(stmt: Select, principal: User) -> Select:
    return stmt.where(group_access_clause(principal))
