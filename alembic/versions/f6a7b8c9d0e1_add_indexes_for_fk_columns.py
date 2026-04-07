"""add_indexes_for_fk_columns

Add indexes on Ingredient.recipe_id and RawRecipe.source_fk.
These FKs are used in every shopping list aggregation and source
filter query but had no index, causing full table scans.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    existing_indexes = {
        idx["name"]
        for tbl in ("ingredients", "raw_recipes")
        for idx in inspector.get_indexes(tbl)
    }

    if "ix_ingredients_recipe_id" not in existing_indexes:
        op.create_index("ix_ingredients_recipe_id", "ingredients", ["recipe_id"])

    if "ix_raw_recipes_source_fk" not in existing_indexes:
        op.create_index("ix_raw_recipes_source_fk", "raw_recipes", ["source_fk"])


def downgrade() -> None:
    op.drop_index("ix_ingredients_recipe_id", table_name="ingredients")
    op.drop_index("ix_raw_recipes_source_fk", table_name="raw_recipes")
