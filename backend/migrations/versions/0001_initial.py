"""Create users and products.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("telegram_id", name="pk_users"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("image_key", sa.String(length=255), nullable=False),
        sa.Column("creator_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_products_name_not_blank"),
        sa.ForeignKeyConstraint(
            ["creator_telegram_id"], ["users.telegram_id"], name="fk_products_creator_telegram_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("image_key", name="uq_products_image_key"),
    )
    op.create_index("ix_products_created_at_id", "products", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_products_created_at_id", table_name="products")
    op.drop_table("products")
    op.drop_table("users")
