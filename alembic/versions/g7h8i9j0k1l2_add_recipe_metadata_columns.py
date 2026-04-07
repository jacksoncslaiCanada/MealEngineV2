"""add_recipe_metadata_columns

Add Phase A enrichment columns to raw_recipes:
  - prep_time    (integer, minutes)
  - dietary_tags (text, JSON list)
  - spice_level  (varchar 16: mild|medium|hot)
  - servings     (integer)

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-07 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("raw_recipes")}

    if "prep_time" not in existing:
        op.add_column("raw_recipes", sa.Column("prep_time", sa.Integer(), nullable=True))
    if "dietary_tags" not in existing:
        op.add_column("raw_recipes", sa.Column("dietary_tags", sa.Text(), nullable=True))
    if "spice_level" not in existing:
        op.add_column("raw_recipes", sa.Column("spice_level", sa.String(16), nullable=True))
    if "servings" not in existing:
        op.add_column("raw_recipes", sa.Column("servings", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_recipes", "servings")
    op.drop_column("raw_recipes", "spice_level")
    op.drop_column("raw_recipes", "dietary_tags")
    op.drop_column("raw_recipes", "prep_time")
