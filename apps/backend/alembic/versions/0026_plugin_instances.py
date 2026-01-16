"""0026: plugin instances."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0026_plugin_instances"
down_revision = "0025_dynamic_secret_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE plugintype AS ENUM ('inventory', 'secrets', 'automation'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.create_table(
        "plugin_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("type", postgresql.ENUM("inventory", "secrets", "automation", name="plugintype", create_type=False), nullable=False),
        sa.Column("definition_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_plugin_instances_project_id", "plugin_instances", ["project_id"])
    op.create_index("ix_plugin_instances_type", "plugin_instances", ["type"])


def downgrade() -> None:
    op.drop_index("ix_plugin_instances_type", table_name="plugin_instances")
    op.drop_index("ix_plugin_instances_project_id", table_name="plugin_instances")
    op.drop_table("plugin_instances")
    plugin_type = sa.Enum("inventory", "secrets", "automation", name="plugintype")
    plugin_type.drop(op.get_bind(), checkfirst=True)
