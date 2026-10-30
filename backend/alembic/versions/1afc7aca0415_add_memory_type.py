"""add memory type

Revision ID: 1afc7aca0415
Revises:
Create Date: 2026-09-03 17:02:11.586282

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1afc7aca0415"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the new column temporarily as nullable
    op.add_column(
        "user_memories",
        sa.Column(
            "memory_type",
            sa.String(length=50),
            nullable=True,
        ),
    )

    # 2. Fill memory_type for existing memories
    op.execute(
        """
        UPDATE user_memories
        SET memory_type = CASE
            WHEN content ILIKE 'The user''s name is %' THEN 'name'
            WHEN content ILIKE 'The user studies %' THEN 'study'
            WHEN content ILIKE 'The user lives in %' THEN 'location'
            WHEN content ILIKE 'The user speaks %' THEN 'language'
            WHEN content ILIKE 'The user works as %' THEN 'profession'
            WHEN content ILIKE 'The user is % years old.' THEN 'age'
            ELSE 'other'
        END
        WHERE memory_type IS NULL
        """
    )

    # 3. Make the column NOT NULL after backfilling existing rows
    op.alter_column(
        "user_memories",
        "memory_type",
        existing_type=sa.String(length=50),
        nullable=False,
    )

    # 4. Create the index
    op.create_index(
        "ix_user_memories_memory_type",
        "user_memories",
        ["memory_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_memories_memory_type",
        table_name="user_memories",
    )

    op.drop_column(
        "user_memories",
        "memory_type",
    )