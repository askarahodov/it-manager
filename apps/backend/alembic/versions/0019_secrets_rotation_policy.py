"""0019: secrets rotation policy."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0019_secrets_rotation_policy"
down_revision = "0018_secrets_expires_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.secrets')")).scalar()
    if not existing:
        return
    op.add_column("secrets", sa.Column("rotation_interval_days", sa.Integer(), nullable=True))
    op.add_column("secrets", sa.Column("last_rotated_at", sa.DateTime(), nullable=True))
    op.add_column("secrets", sa.Column("next_rotated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.secrets')")).scalar()
    if not existing:
        return
    op.drop_column("secrets", "next_rotated_at")
    op.drop_column("secrets", "last_rotated_at")
    op.drop_column("secrets", "rotation_interval_days")
