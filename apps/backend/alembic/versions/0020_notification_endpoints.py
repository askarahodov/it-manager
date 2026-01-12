"""0020: notification endpoints."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0020_notification_endpoints"
down_revision = "0019_secrets_rotation_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.notification_endpoints')")).scalar()
    if existing:
        return
    op.create_table(
        "notification_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, server_default="1"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="webhook"),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("secret", sa.String(), nullable=True),
        sa.Column("events", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_notification_endpoints_id", "notification_endpoints", ["id"])
    op.create_index("ix_notification_endpoints_project_id", "notification_endpoints", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.notification_endpoints')")).scalar()
    if not existing:
        return
    op.drop_index("ix_notification_endpoints_project_id", table_name="notification_endpoints")
    op.drop_index("ix_notification_endpoints_id", table_name="notification_endpoints")
    op.drop_table("notification_endpoints")
