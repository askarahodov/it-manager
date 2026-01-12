"""add host check_method

Revision ID: 0002_host_check_method
Revises: 0001_init_schema
Create Date: 2025-12-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0002_host_check_method"
down_revision = "0001_init_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    check_method = sa.Enum("ping", "tcp", "ssh", name="hostcheckmethod")
    check_method.create(op.get_bind(), checkfirst=True)
    op.add_column("hosts", sa.Column("check_method", check_method, nullable=False, server_default="tcp"))
    op.alter_column("hosts", "check_method", server_default=None)


def downgrade() -> None:
    op.drop_column("hosts", "check_method")
    check_method = sa.Enum("ping", "tcp", "ssh", name="hostcheckmethod")
    check_method.drop(op.get_bind(), checkfirst=True)

