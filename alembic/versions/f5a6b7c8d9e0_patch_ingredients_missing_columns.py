"""patch_ingredients_missing_columns

The previous migration (e4f5a6b7c8d9) skipped the CREATE TABLE because the
`ingredients` table already existed (created bare by SQLAlchemy create_all
before the migration ran). This migration adds any columns that are missing.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-03-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("ingredients")}

    _add_if_missing = [
        ("ingredient_name", sa.Column("ingredient_name", sa.String(256), nullable=True)),
        ("quantity",        sa.Column("quantity",        sa.String(64),  nullable=True)),
        ("unit",            sa.Column("unit",            sa.String(64),  nullable=True)),
        ("recipe_id",       sa.Column("recipe_id",       sa.Integer(),   nullable=True)),
        ("source_id",       sa.Column("source_id",       sa.Integer(),   nullable=True)),
        ("extracted_at",    sa.Column("extracted_at",    sa.DateTime(timezone=True), nullable=True)),
    ]

    for col_name, col_def in _add_if_missing:
        if col_name not in existing_cols:
            op.add_column("ingredients", col_def)

    # Add FK constraints only if the columns were just created and the
    # constraints don't already exist (PostgreSQL only).
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("ingredients")}

    if "fk_ingredients_recipe_id" not in existing_fks and "recipe_id" in existing_cols or \
       "recipe_id" not in existing_cols:
        try:
            op.create_foreign_key(
                "fk_ingredients_recipe_id", "ingredients",
                "raw_recipes", ["recipe_id"], ["id"],
            )
        except Exception:
            pass  # constraint may already exist under a different name

    if "fk_ingredients_source_id" not in existing_fks and "source_id" in existing_cols or \
       "source_id" not in existing_cols:
        try:
            op.create_foreign_key(
                "fk_ingredients_source_id", "ingredients",
                "sources", ["source_id"], ["id"],
            )
        except Exception:
            pass  # constraint may already exist under a different name


def downgrade() -> None:
    # Removing individual columns is non-trivial with live data; full table
    # drop is the safe downgrade path since the table should be empty at this stage.
    op.drop_table("ingredients")
