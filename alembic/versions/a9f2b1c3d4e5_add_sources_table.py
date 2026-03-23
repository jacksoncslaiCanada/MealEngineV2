"""add_sources_table

Revision ID: a9f2b1c3d4e5
Revises: 3e1385ebf5eb
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


# revision identifiers, used by Alembic.
revision: str = 'a9f2b1c3d4e5'
down_revision: Union[str, None] = '3e1385ebf5eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    existing_tables = inspector.get_table_names()

    if "sources" not in existing_tables:
        op.create_table(
            "sources",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("platform", sa.String(length=16), nullable=False),
            sa.Column("handle", sa.String(length=256), nullable=False),
            sa.Column("display_name", sa.String(length=256), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("quality_score", sa.Float(), nullable=True),
            sa.Column("content_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("platform", "handle", name="uq_source_platform_handle"),
        )

    existing_columns = {c["name"] for c in inspector.get_columns("raw_recipes")}

    if "source_fk" not in existing_columns:
        op.add_column("raw_recipes", sa.Column(
            "source_fk", sa.Integer(),
            sa.ForeignKey("sources.id"),
            nullable=True,
        ))
    if "engagement_score" not in existing_columns:
        op.add_column("raw_recipes", sa.Column("engagement_score", sa.Float(), nullable=True))
    if "content_length" not in existing_columns:
        op.add_column("raw_recipes", sa.Column("content_length", sa.Integer(), nullable=True))
    if "has_transcript" not in existing_columns:
        op.add_column("raw_recipes", sa.Column("has_transcript", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_recipes", "has_transcript")
    op.drop_column("raw_recipes", "content_length")
    op.drop_column("raw_recipes", "engagement_score")
    op.drop_column("raw_recipes", "source_fk")
    op.drop_table("sources")
