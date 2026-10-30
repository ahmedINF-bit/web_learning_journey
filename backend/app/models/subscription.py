from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_subscriptions_user_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    plan = Column(String(20), default="free")
    messages_used = Column(Integer, default=0)
    usage_date = Column(Date, nullable=True)
    messages_limit = Column(Integer, default=50)

    is_active = Column(Boolean, default=True)
    started_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user = relationship(
        "User",
        back_populates="subscription",
    )