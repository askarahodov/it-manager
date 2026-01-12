"""0025: dynamic secret leases."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025_dynamic_secret_leases"
down_revision = "0024_global_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("secrets", sa.Column("dynamic_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("secrets", sa.Column("dynamic_ttl_seconds", sa.Integer(), nullable=True))
    op.create_table(
        "secret_leases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("secret_id", sa.Integer(), sa.ForeignKey("secrets.id"), nullable=False),
        sa.Column("issued_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("issued_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
    )
    op.create_index("ix_secret_leases_secret_id", "secret_leases", ["secret_id"])
    op.create_index("ix_secret_leases_project_id", "secret_leases", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_secret_leases_project_id", table_name="secret_leases")
    op.drop_index("ix_secret_leases_secret_id", table_name="secret_leases")
    op.drop_table("secret_leases")
    op.drop_column("secrets", "dynamic_ttl_seconds")
    op.drop_column("secrets", "dynamic_enabled")
