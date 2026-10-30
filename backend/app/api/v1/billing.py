import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.billing_order import BillingOrder
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.billing import (
    BillingCheckoutRequest,
    BillingOrderResponse,
)
from app.services.billing_service import (
    BillingConfigurationError,
    BillingProviderError,
    create_chargily_checkout,
    get_plan_price_dzd,
    retrieve_chargily_checkout,
    verify_chargily_webhook_signature,
)
from app.services.subscription_service import get_plan_daily_limit


router = APIRouter(prefix="/billing", tags=["Billing"])


def require_billing_configuration() -> None:
    if not settings.BILLING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not enabled.",
        )

    if not settings.CHARGILY_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider is not configured.",
        )

    webhook_url = settings.CHARGILY_WEBHOOK_ENDPOINT or ""
    parsed_webhook = urlparse(webhook_url)

    if (
        parsed_webhook.scheme != "https"
        or not parsed_webhook.hostname
        or parsed_webhook.hostname.lower() in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A public HTTPS webhook endpoint is required.",
        )

    frontend_url = urlparse(settings.FRONTEND_URL)

    if not frontend_url.hostname:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The frontend URL is not configured.",
        )

    if settings.CHARGILY_MODE == "live" and frontend_url.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live billing requires an HTTPS frontend URL.",
        )

    if settings.BILLING_SUBSCRIPTION_DAYS < 1:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subscription duration is not configured.",
        )


@router.post(
    "/checkout",
    response_model=BillingOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout(
    data: BillingCheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_billing_configuration()

    try:
        amount = get_plan_price_dzd(data.plan)
    except BillingConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    order_reference = f"talaba_{__import__('uuid').uuid4().hex}"

    order = BillingOrder(
        user_id=user.id,
        plan=data.plan,
        amount_dzd=amount,
        currency="dzd",
        order_reference=order_reference,
        status="pending",
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    try:
        checkout_id, checkout_url = await create_chargily_checkout(
            plan=order.plan,
            amount_dzd=order.amount_dzd,
            order_reference=order.order_reference,
        )
    except BillingConfigurationError as exc:
        order.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except BillingProviderError as exc:
        order.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not create a payment checkout.",
        ) from exc

    order.provider_checkout_id = checkout_id
    order.checkout_url = checkout_url

    await db.commit()
    await db.refresh(order)

    return order


@router.get(
    "/orders/{order_reference}",
    response_model=BillingOrderResponse,
)
async def get_billing_order(
    order_reference: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BillingOrder).where(
            BillingOrder.order_reference == order_reference,
            BillingOrder.user_id == user.id,
        )
    )
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Billing order not found.",
        )

    return order


@router.post("/webhook")
async def chargily_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not settings.CHARGILY_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider is not configured.",
        )

    raw_payload = await request.body()
    signature = request.headers.get("signature")

    if not verify_chargily_webhook_signature(raw_payload, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature.",
        )

    try:
        event = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload.",
        ) from exc

    if not isinstance(event, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook event.",
        )

    event_type = event.get("type")
    checkout = event.get("data")

    if not isinstance(checkout, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid checkout event data.",
        )

    # The event's live/test flag is an additional consistency check.
    # The HMAC signature remains the primary authenticity check.
    live_flag = event.get("livemode")

    if live_flag is not None:
        if isinstance(live_flag, bool):
            event_is_live = live_flag
        else:
            event_is_live = str(live_flag).strip().lower() in {
                "true",
                "1",
                "yes",
            }

        if event_is_live != (settings.CHARGILY_MODE == "live"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook mode does not match billing configuration.",
            )

    if event_type not in {
        "checkout.paid",
        "checkout.failed",
        "checkout.canceled",
        "checkout.cancelled",
        "checkout.expired",
    }:
        return {"received": True}

    checkout_id = checkout.get("id")

    if not isinstance(checkout_id, str) or not checkout_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing checkout ID.",
        )

    result = await db.execute(
        select(BillingOrder)
        .where(BillingOrder.provider_checkout_id == checkout_id)
        .with_for_update()
    )
    order = result.scalar_one_or_none()

       # Ignore valid events for checkouts that do not belong to this application.
    if order is None:
        return {"received": True}

    if event_type == "checkout.paid":
        # Prevent duplicate deliveries from extending subscriptions twice.
        if order.status == "paid":
            return {"received": True}

        # Verify the canonical checkout directly with Chargily.
        try:
            verified_checkout = await retrieve_chargily_checkout(
                checkout_id=checkout_id
            )
        except BillingConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment verification is not configured correctly.",
            ) from exc
        except BillingProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not verify payment with the provider.",
            ) from exc

        amount = verified_checkout.get("amount")
        currency = str(
            verified_checkout.get("currency") or ""
        ).lower()
        provider_livemode = verified_checkout.get("livemode")

        if (
            verified_checkout.get("id") != checkout_id
            or verified_checkout.get("status") != "paid"
            or type(amount) is not int
            or amount != order.amount_dzd
            or currency != order.currency.lower()
            or type(provider_livemode) is not bool
            or provider_livemode != (settings.CHARGILY_MODE == "live")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verified payment details do not match the billing order.",
            )

        now = datetime.now(timezone.utc)

        subscription_result = await db.execute(
            select(Subscription)
            .where(Subscription.user_id == order.user_id)
            .with_for_update()
        )
        subscription = subscription_result.scalar_one_or_none()

        daily_limit = get_plan_daily_limit(order.plan)
        expires_at = now + timedelta(
            days=settings.BILLING_SUBSCRIPTION_DAYS
        )

        if subscription is None:
            subscription = Subscription(
                user_id=order.user_id,
                plan=order.plan,
                messages_used=0,
                messages_limit=daily_limit,
                usage_date=now.date(),
                is_active=True,
                started_at=now,
                expires_at=expires_at,
            )
            db.add(subscription)
        else:
            # Preserve remaining time when an active subscription is renewed.
            existing_expiry = subscription.expires_at

            if existing_expiry is not None:
                if existing_expiry.tzinfo is None:
                    existing_expiry = existing_expiry.replace(
                        tzinfo=timezone.utc
                    )

                if subscription.is_active and existing_expiry > now:
                    expires_at = existing_expiry + timedelta(
                        days=settings.BILLING_SUBSCRIPTION_DAYS
                    )

            subscription.plan = order.plan
            subscription.messages_limit = daily_limit
            subscription.is_active = True
            subscription.started_at = now
            subscription.expires_at = expires_at

        order.status = "paid"
        order.paid_at = now

        # Persist the order and subscription together before acknowledging.
        await db.commit()
        return {"received": True}

    # Failure/cancellation events must never downgrade an already paid order.
    if order.status != "paid":
        order.status = {
            "checkout.failed": "failed",
            "checkout.canceled": "canceled",
            "checkout.cancelled": "canceled",
            "checkout.expired": "expired",
        }[event_type]
        await db.commit()

    return {"received": True}
