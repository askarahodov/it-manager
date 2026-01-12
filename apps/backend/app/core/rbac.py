"""RBAC 2.0: роли и пермишены.

Цели:
- дать более гибкую матрицу прав, чем admin/user;
- оставить реализацию достаточно простой для MVP (правила роли задаются кодом);
- подготовить почву для последующей гранулярности по проектам/группам/окружениям.
"""

from __future__ import annotations

import enum
from typing import Iterable


class Permission(str, enum.Enum):
    # Projects (tenants)
    projects_read = "projects.read"
    projects_write = "projects.write"

    # Hosts
    hosts_read = "hosts.read"
    hosts_write = "hosts.write"
    hosts_check = "hosts.check"
    hosts_ssh = "hosts.ssh"

    # Secrets
    secrets_read_metadata = "secrets.read_metadata"
    secrets_write = "secrets.write"
    secrets_reveal = "secrets.reveal"
    secrets_use = "secrets.use"

    # Automation / Ansible
    ansible_read = "ansible.read"
    ansible_run = "ansible.run"
    ansible_edit = "ansible.edit"
    ansible_schedule = "ansible.schedule"


# Роли. Источник истины по значениям — enum в app.db.models.UserRole.
# Здесь держим только матрицу прав.
ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": set(Permission),
    "operator": {
        Permission.projects_read,
        Permission.hosts_read,
        Permission.hosts_write,
        Permission.hosts_check,
        Permission.hosts_ssh,
        Permission.secrets_read_metadata,
        Permission.secrets_use,
        Permission.ansible_read,
        Permission.ansible_run,
    },
    "viewer": {
        Permission.projects_read,
        Permission.hosts_read,
        Permission.secrets_read_metadata,
        Permission.ansible_read,
    },
    # Ограниченная роль для запуска автоматизации (например, из CI/внешней системы).
    "automation-only": {
        Permission.projects_read,
        Permission.hosts_read,
        Permission.secrets_read_metadata,
        Permission.secrets_use,
        Permission.ansible_read,
        Permission.ansible_run,
        Permission.ansible_schedule,
    },
    # Для обратной совместимости со старым RBAC admin/user.
    "user": {
        Permission.projects_read,
        Permission.hosts_read,
        Permission.secrets_read_metadata,
        Permission.ansible_read,
    },
}


def has_permission(role: str | None, permission: Permission) -> bool:
    if not role:
        return False
    perms = ROLE_PERMISSIONS.get(role)
    if perms is None:
        return False
    return permission in perms


def has_any_permission(role: str | None, permissions: Iterable[Permission]) -> bool:
    if not role:
        return False
    perms = ROLE_PERMISSIONS.get(role)
    if perms is None:
        return False
    return any(p in perms for p in permissions)
