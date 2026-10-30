from sqlalchemy import Integer, Text, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserMemory(Base):
    __tablename__ = "user_memories"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "memory_type",
            name="uq_user_memory_user_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    memory_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="memories",
    )