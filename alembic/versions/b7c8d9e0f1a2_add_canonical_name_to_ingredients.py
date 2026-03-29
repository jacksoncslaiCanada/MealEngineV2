"""add_canonical_name_to_ingredients

Adds a nullable, indexed canonical_name column to the ingredients table.
Populated at extraction time by normalise_ingredient().

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-03-29 02:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_cols = {c["name"] for c in sa.inspect(conn).get_columns("ingredients")}
    if "canonical_name" not in existing_cols:
        op.add_column(
            "ingredients",
            sa.Column("canonical_name", sa.String(256), nullable=True),
        )
        op.create_index("ix_ingredients_canonical_name", "ingredients", ["canonical_name"])


def downgrade() -> None:
    op.drop_index("ix_ingredients_canonical_name", table_name="ingredients")
    op.drop_column("ingredients", "canonical_name")
