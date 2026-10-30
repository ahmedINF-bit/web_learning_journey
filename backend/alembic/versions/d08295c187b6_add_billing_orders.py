"""add billing orders

Revision ID: d08295c187b6
Revises: b91d6e7a3c42
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d08295c187b6"
down_revision: Union[str, None] = "b91d6e7a3c42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("amount_dzd", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("order_reference", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_checkout_id", sa.String(length=128), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_checkout_id"),
    )

    op.create_index(
        "ix_billing_orders_id",
        "billing_orders",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_billing_orders_user_id",
        "billing_orders",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_billing_orders_order_reference",
        "billing_orders",
        ["order_reference"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_billing_orders_order_reference",
        table_name="billing_orders",
    )
    op.drop_index(
        "ix_billing_orders_user_id",
        table_name="billing_orders",
    )
    op.drop_index(
        "ix_billing_orders_id",
        table_name="billing_orders",
    )
    op.drop_table("billing_orders")
