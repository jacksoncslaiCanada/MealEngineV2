"""add_subscribers_table

Adds the subscribers table for Tier 1 automation:
  - email, variant, plans_remaining (starts at 4)
  - gumroad_order_id for linking purchases
  - active flag for soft-disabling
  - purchased_at, last_sent_at, created_at timestamps

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-08 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    if "subscribers" in inspector.get_table_names():
        return  # idempotent

    op.create_table(
        "subscribers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(256), nullable=False, unique=True),
        sa.Column("variant", sa.String(32), nullable=False),
        sa.Column("plans_remaining", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("gumroad_order_id", sa.String(256), nullable=True, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_subscribers_email", "subscribers", ["email"])
    op.create_index("ix_subscribers_variant_active", "subscribers", ["variant", "active"])


def downgrade() -> None:
    op.drop_index("ix_subscribers_variant_active", table_name="subscribers")
    op.drop_index("ix_subscribers_email", table_name="subscribers")
    op.drop_table("subscribers")
