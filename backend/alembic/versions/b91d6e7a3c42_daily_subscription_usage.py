"""Add daily subscription usage tracking and one subscription per user."""

from alembic import op
import sqlalchemy as sa

revision = "b91d6e7a3c42"
down_revision = "6b7e767a78c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("usage_date", sa.Date(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_subscriptions_user_id",
        "subscriptions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_subscriptions_user_id",
        "subscriptions",
        type_="unique",
    )
    op.drop_column("subscriptions", "usage_date")
