"""add_classification_columns_and_meal_plans

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-04-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    # --- Add classification columns to raw_recipes ---
    existing_cols = {c["name"] for c in inspector.get_columns("raw_recipes")}
    for col_name, col_def in [
        ("difficulty", sa.Column("difficulty", sa.String(16),  nullable=True)),
        ("cuisine",    sa.Column("cuisine",    sa.String(64),  nullable=True)),
        ("meal_type",  sa.Column("meal_type",  sa.String(16),  nullable=True)),
    ]:
        if col_name not in existing_cols:
            op.add_column("raw_recipes", col_def)

    # --- Create meal_plans table ---
    existing_tables = inspector.get_table_names()
    if "meal_plans" not in existing_tables:
        op.create_table(
            "meal_plans",
            sa.Column("id",            sa.Integer(),                    primary_key=True, autoincrement=True),
            sa.Column("variant",       sa.String(32),                   nullable=False),
            sa.Column("week_label",    sa.String(16),                   nullable=False),
            sa.Column("plan_json",     sa.Text(),                       nullable=False),
            sa.Column("shopping_json", sa.Text(),                       nullable=False),
            sa.Column("pdf_data",      sa.LargeBinary(),                nullable=True),
            sa.Column("created_at",    sa.DateTime(timezone=True),      nullable=False),
        )


def downgrade() -> None:
    op.drop_table("meal_plans")
    for col in ("difficulty", "cuisine", "meal_type"):
        op.drop_column("raw_recipes", col)
