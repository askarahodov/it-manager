"""0008: hosts last automation run status.

Adds to hosts:
- last_run_id
- last_run_status
- last_run_at
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0008_hosts_last_run_status"
down_revision = "0007_normalize_secret_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if not existing:
        return
    with op.batch_alter_table("hosts") as batch:
        batch.add_column(sa.Column("last_run_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("last_run_status", sa.String(), nullable=True))
        batch.add_column(sa.Column("last_run_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if not existing:
        return
    with op.batch_alter_table("hosts") as batch:
        batch.drop_column("last_run_at")
        batch.drop_column("last_run_status")
        batch.drop_column("last_run_id")

