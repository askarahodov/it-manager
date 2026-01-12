"""0005: users.allowed_project_ids (ограничение доступа по проектам).

Добавляет в users JSONB поле allowed_project_ids:
- NULL => доступны все проекты
- []   => нет доступа ни к одному проекту
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0005_users_allowed_projects"
down_revision = "0004_projects_tenants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.users')")).scalar()
    if not existing:
        return
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("allowed_project_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.users')")).scalar()
    if not existing:
        return
    with op.batch_alter_table("users") as batch:
        batch.drop_column("allowed_project_ids")
