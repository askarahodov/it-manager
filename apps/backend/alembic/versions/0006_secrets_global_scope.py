"""0006: secrets.project_id nullable for global shared secrets.

Policy:
- project_id NULL => secret is global (shared across projects)
- project_id set  => secret is project-scoped
"""

from alembic import op
from sqlalchemy import text

revision = "0006_secrets_global_scope"
down_revision = "0005_users_allowed_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.secrets')")).scalar()
    if not existing:
        return
    with op.batch_alter_table("secrets") as batch:
        batch.alter_column("project_id", existing_type=None, nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.secrets')")).scalar()
    if not existing:
        return
    # Best-effort: assign NULL project_id to default project (1) before making NOT NULL.
    bind.execute(text("UPDATE secrets SET project_id = 1 WHERE project_id IS NULL"))
    with op.batch_alter_table("secrets") as batch:
        batch.alter_column("project_id", existing_type=None, nullable=False)

