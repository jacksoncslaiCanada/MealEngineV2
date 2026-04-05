"""patch_meal_plans_missing_columns

If meal_plans was created by create_all before the migration ran it may
exist but be missing columns. This migration adds any that are absent.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-05 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    # ── Patch raw_recipes classification columns ──────────────────────────────
    rr_cols = {c["name"] for c in inspector.get_columns("raw_recipes")}
    for col_name, col_def in [
        ("difficulty", sa.Column("difficulty", sa.String(16), nullable=True)),
        ("cuisine",    sa.Column("cuisine",    sa.String(64), nullable=True)),
        ("meal_type",  sa.Column("meal_type",  sa.String(16), nullable=True)),
    ]:
        if col_name not in rr_cols:
            op.add_column("raw_recipes", col_def)

    # ── Ensure meal_plans table exists with all columns ───────────────────────
    existing_tables = inspector.get_table_names()
    if "meal_plans" not in existing_tables:
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
    else:
        # Table exists — add any missing columns
        mp_cols = {c["name"] for c in inspector.get_columns("meal_plans")}
        for col_name, col_def in [
            ("variant",       sa.Column("variant",       sa.String(32),              nullable=True)),
            ("week_label",    sa.Column("week_label",    sa.String(16),              nullable=True)),
            ("plan_json",     sa.Column("plan_json",     sa.Text(),                  nullable=True)),
            ("shopping_json", sa.Column("shopping_json", sa.Text(),                  nullable=True)),
            ("pdf_data",      sa.Column("pdf_data",      sa.LargeBinary(),           nullable=True)),
            ("created_at",    sa.Column("created_at",    sa.DateTime(timezone=True), nullable=True)),
        ]:
            if col_name not in mp_cols:
                op.add_column("meal_plans", col_def)


def downgrade() -> None:
    pass
