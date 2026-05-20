"""add gumroad_sales table

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-05-20

"""
from alembic import op
import sqlalchemy as sa

revision = 'r8s9t0u1v2w3'
down_revision = 'q7r8s9t0u1v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gumroad_sales',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('order_id', sa.String(256), nullable=False, unique=True),
        sa.Column('email', sa.String(256), nullable=False),
        sa.Column('product_permalink', sa.String(256), nullable=False),
        sa.Column('pdf_path', sa.String(512), nullable=False),
        sa.Column('delivered', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('gumroad_sales')
