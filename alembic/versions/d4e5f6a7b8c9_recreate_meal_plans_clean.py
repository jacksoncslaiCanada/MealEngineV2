"""recreate_meal_plans_clean

Drop the legacy meal_plans table (which has unknown NOT NULL columns from
an older schema) and recreate it with only the columns the current model
needs.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-05 03:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    if "meal_plans" in inspector.get_table_names():
        # CASCADE drops the meal_plan_recipes FK constraint too
        op.execute("DROP TABLE meal_plans CASCADE")

    op.create_table(
        "meal_plans",
        sa.Column("id",            sa.Integer(),               primary_key=True, autoincrement=True),
        sa.Column("variant",       sa.String(32),              nullable=False),
        sa.Column("week_label",    sa.String(16),              nullable=False),
        sa.Column("plan_json",     sa.Text(),                  nullable=False),
        sa.Column("shopping_json", sa.Text(),                  nullable=False),
        sa.Column("pdf_data",      sa.LargeBinary(),           nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("meal_plans")
