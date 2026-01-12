"""0007: normalize Secret.scope values after introducing global secrets.

Historical behavior:
- scope default was "global" even for project-scoped secrets.

New policy:
- project_id IS NULL => scope = "global"
- project_id IS NOT NULL => scope = "project"
"""

from alembic import op
from sqlalchemy import text

revision = "0007_normalize_secret_scope"
down_revision = "0006_secrets_global_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.secrets')")).scalar()
    if not existing:
        return
    bind.execute(text("UPDATE secrets SET scope = 'global' WHERE project_id IS NULL"))
    bind.execute(text("UPDATE secrets SET scope = 'project' WHERE project_id IS NOT NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.secrets')")).scalar()
    if not existing:
        return
    # Best-effort revert to old default label.
    bind.execute(text("UPDATE secrets SET scope = 'global'"))

