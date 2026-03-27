"""add_ingredients_table

Creates the `ingredients` table for Phase 2 — structured ingredient records
extracted from raw recipes by Claude.

Each row represents one ingredient extracted from one raw recipe, with FKs
back to both `raw_recipes` (recipe_id) and `sources` (source_id, denormalized
for direct per-platform queries without an extra join).

The upgrade is idempotent: if the table already exists the CREATE is skipped.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-03-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    if "ingredients" not in inspector.get_table_names():
        op.create_table(
            "ingredients",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ingredient_name", sa.String(length=256), nullable=False),
            sa.Column("quantity", sa.String(length=64), nullable=True),
            sa.Column("unit", sa.String(length=64), nullable=True),
            sa.Column("recipe_id", sa.Integer(), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["recipe_id"], ["raw_recipes.id"], name="fk_ingredients_recipe_id"),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_ingredients_source_id"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("ingredients")
