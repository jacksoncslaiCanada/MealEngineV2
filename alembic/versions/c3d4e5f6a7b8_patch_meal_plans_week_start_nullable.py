"""patch_meal_plans_week_start_nullable

The pre-existing meal_plans table has a week_start NOT NULL column that
the current model doesn't populate. Make it nullable so inserts succeed.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-05 02:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect, text


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    if "meal_plans" not in inspector.get_table_names():
        return

    cols = {c["name"]: c for c in inspector.get_columns("meal_plans")}

    # Make week_start nullable if it exists with a NOT NULL constraint
    if "week_start" in cols and not cols["week_start"]["nullable"]:
        op.alter_column("meal_plans", "week_start", nullable=True)

    # Make any other legacy NOT NULL columns nullable
    for col_name in ("week_end", "title", "notes"):
        if col_name in cols and not cols[col_name]["nullable"]:
            op.alter_column("meal_plans", col_name, nullable=True)


def downgrade() -> None:
    pass
