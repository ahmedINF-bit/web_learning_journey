from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.core.database import Base


class BillingOrder(Base):
    __tablename__ = "billing_orders"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Server-selected plan and amount.
    plan = Column(String(20), nullable=False)
    amount_dzd = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="dzd")

    # Unique internal reference for matching provider events.
    order_reference = Column(String(64), nullable=False, unique=True, index=True)

    status = Column(String(20), nullable=False, default="pending")

    provider_checkout_id = Column(
        String(128),
        nullable=True,
        unique=True,
    )

    checkout_url = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paid_at = Column(DateTime(timezone=True), nullable=True)
