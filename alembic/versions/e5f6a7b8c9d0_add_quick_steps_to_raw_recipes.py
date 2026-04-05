"""add_quick_steps_to_raw_recipes

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-05 04:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("raw_recipes")}
    if "quick_steps" not in existing_cols:
        op.add_column("raw_recipes", sa.Column("quick_steps", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_recipes", "quick_steps")
