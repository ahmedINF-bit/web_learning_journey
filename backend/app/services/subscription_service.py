from collections.abc import AsyncGenerator
from datetime import date, datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.subscription import Subscription
from app.models.user import User
PLAN_DAILY_LIMITS: dict[str, int] = {
    "free": 50,
    "pro": 200,
    "enterprise": 1000,
}


def get_plan_daily_limit(plan: str | None) -> int:
    normalized_plan = str(plan or "").strip().lower()

    if normalized_plan not in PLAN_DAILY_LIMITS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unknown subscription plan.",
        )

    return PLAN_DAILY_LIMITS[normalized_plan]


async def reserve_ai_usage(user_id: int, db: AsyncSession) -> date:
    """Reserve one daily AI request. Row locking serializes existing subscriptions."""
    now = datetime.now(timezone.utc)
    today = now.date()

    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .with_for_update()
    )
    subscription = result.scalar_one_or_none()

    if subscription is None:
        subscription = Subscription(
            user_id=user_id,
            plan="free",
            messages_used=0,
            messages_limit=50,
            is_active=True,
            usage_date=today,
        )
        try:
            # The unique constraint and savepoint handle concurrent first requests.
            async with db.begin_nested():
                db.add(subscription)
                await db.flush()
        except IntegrityError:
            result = await db.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .with_for_update()
            )
            subscription = result.scalar_one_or_none()
            if subscription is None:
                raise

    if not subscription.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your subscription is inactive.",
        )

    expires_at = subscription.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your subscription has expired.",
            )

    if subscription.usage_date != today:
        subscription.messages_used = 0
        subscription.usage_date = today

    limit = get_plan_daily_limit(subscription.plan)
    subscription.messages_limit = limit

    used = int(subscription.messages_used or 0)

    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "daily_ai_limit_reached",
                "message": f"Daily AI limit reached ({limit} requests). Try again after 00:00 UTC.",
                "limit": limit,
                "used": used,
                "resets_at": "00:00 UTC",
            },
        )

    subscription.messages_used = used + 1
    # Persist the reservation and release the lock before making the slower AI call.
    await db.commit()
    return today


async def refund_ai_usage(user_id: int, usage_date: date, db: AsyncSession) -> None:
    """Refund one reservation if generation fails on the same UTC day."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .with_for_update()
    )
    subscription = result.scalar_one_or_none()
    if (
        subscription is not None
        and subscription.usage_date == usage_date
        and int(subscription.messages_used or 0) > 0
    ):
        subscription.messages_used = int(subscription.messages_used or 0) - 1
        await db.commit()
    else:
        await db.rollback()


async def enforce_ai_quota(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[None, None]:
    """Reserve quota before an AI endpoint and refund when the endpoint fails."""
    usage_date = await reserve_ai_usage(user.id, db)
    try:
        yield
    except Exception:
        # Roll back user-message/partial endpoint writes before refunding the reservation.
        await db.rollback()
        try:
            await refund_ai_usage(user.id, usage_date, db)
        except Exception:
            await db.rollback()
        raise
