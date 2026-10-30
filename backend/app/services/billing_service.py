from urllib.parse import quote, urlparse
import hashlib
import hmac
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class BillingConfigurationError(RuntimeError):
    """Billing is not configured sufficiently to create real checkouts."""


class BillingProviderError(RuntimeError):
    """Chargily rejected a request or returned an invalid response."""


def get_plan_price_dzd(plan: str) -> int:
    prices = {
        "pro": settings.BILLING_PRO_PRICE_DZD,
        "enterprise": settings.BILLING_ENTERPRISE_PRICE_DZD,
    }

    price = prices.get(plan)

    if type(price) is not int or price <= 0:
        raise BillingConfigurationError(
            f"The DZD price for the {plan} plan is not configured."
        )

    return price


def verify_chargily_webhook_signature(
    payload: bytes,
    signature: str | None,
) -> bool:
    """Verify Chargily's signature against the exact raw request body."""
    secret = settings.CHARGILY_API_KEY

    if not secret or not signature:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature.strip())

async def retrieve_chargily_checkout(*, checkout_id: str) -> dict:
    """Retrieve the canonical checkout details from Chargily."""
    if not settings.CHARGILY_API_KEY:
        raise BillingConfigurationError(
            "The Chargily API key is not configured."
        )

    if not isinstance(checkout_id, str) or not checkout_id.strip():
        raise BillingProviderError("Invalid checkout ID.")

    if settings.CHARGILY_MODE == "test":
        endpoint = "https://pay.chargily.net/test/api/v2/checkouts"
    elif settings.CHARGILY_MODE == "live":
        endpoint = "https://pay.chargily.net/api/v2/checkouts"
    else:
        raise BillingConfigurationError("Invalid Chargily mode.")

    url = f"{endpoint}/{quote(checkout_id, safe='')}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {settings.CHARGILY_API_KEY}",
                    "Accept": "application/json",
                },
            )

        if not response.is_success:
            try:
                provider_error = response.json()
            except ValueError:
                provider_error = response.text[:500]

            if isinstance(provider_error, dict):
                provider_error = {
                    key: provider_error[key]
                    for key in ("message", "error", "errors", "code")
                    if key in provider_error
                }
            else:
                provider_error = str(provider_error)[:500]

            logger.warning(
                "Chargily checkout retrieval failed (HTTP %s): %s",
                response.status_code,
                provider_error,
            )

            raise BillingProviderError(
                f"Chargily returned HTTP {response.status_code}."
            )

        data = response.json()

    except BillingProviderError:
        raise
    except httpx.TimeoutException as exc:
        raise BillingProviderError(
            "Timed out while verifying the checkout."
        ) from exc
    except httpx.RequestError as exc:
        raise BillingProviderError(
            "Could not connect to Chargily to verify the checkout."
        ) from exc
    except ValueError as exc:
        raise BillingProviderError(
            "Chargily returned an invalid checkout response."
        ) from exc

    if not isinstance(data, dict):
        raise BillingProviderError(
            "Chargily returned an invalid checkout object."
        )

    if data.get("id") != checkout_id:
        raise BillingProviderError(
            "Chargily returned a different checkout ID."
        )

    return data

async def create_chargily_checkout(
    *,
    plan: str,
    amount_dzd: int,
    order_reference: str,
) -> tuple[str, str]:
    """Create a hosted Chargily checkout. Never expose the secret key."""
    if not settings.CHARGILY_API_KEY:
        raise BillingConfigurationError(
            "The Chargily API key is not configured."
        )

    webhook_endpoint = settings.CHARGILY_WEBHOOK_ENDPOINT
    if not webhook_endpoint:
        raise BillingConfigurationError(
            "The Chargily webhook endpoint is not configured."
        )

    mode = settings.CHARGILY_MODE
    if mode == "test":
        endpoint = "https://pay.chargily.net/test/api/v2/checkouts"
    elif mode == "live":
        endpoint = "https://pay.chargily.net/api/v2/checkouts"
    else:
        raise BillingConfigurationError("Invalid Chargily mode.")

    frontend_url = settings.FRONTEND_URL.rstrip("/")
    payload = {
        "amount": amount_dzd,
        "currency": "dzd",
        "success_url": (
            f"{frontend_url}/app/subscription"
            f"?billing=success&order={order_reference}"
        ),
        "failure_url": (
            f"{frontend_url}/app/subscription"
            f"?billing=failure&order={order_reference}"
        ),
        "webhook_endpoint": webhook_endpoint,
        "description": f"Talaba AI {plan.title()} subscription",
        "locale": "ar",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.CHARGILY_API_KEY}",
                    "Content-Type": "application/json",
                },
            )

        if not response.is_success:
            try:
                provider_error = response.json()
            except ValueError:
                provider_error = response.text[:500]

            if isinstance(provider_error, dict):
                provider_error = {
                    key: provider_error[key]
                    for key in ("message", "error", "errors", "code")
                    if key in provider_error
                }
            else:
                provider_error = str(provider_error)[:500]

            logger.warning(
                "Chargily checkout creation failed (HTTP %s): %s",
                response.status_code,
                provider_error,
            )

            raise BillingProviderError(
                f"Chargily returned HTTP {response.status_code}."
            )

        data = response.json()

    except BillingProviderError:
        raise
    except httpx.TimeoutException as exc:
        logger.warning("Chargily checkout creation timed out.")
        raise BillingProviderError(
            "The Chargily request timed out."
        ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "Chargily checkout connection failed (%s): %s",
            type(exc).__name__,
            str(exc),
        )
        raise BillingProviderError(
            "Could not connect to Chargily."
        ) from exc
    except ValueError as exc:
        logger.warning("Chargily returned invalid JSON for checkout creation.")
        raise BillingProviderError(
            "Chargily returned an invalid response."
        ) from exc

    if not isinstance(data, dict):
        logger.warning(
            "Chargily returned a non-object checkout response."
        )
        raise BillingProviderError(
            "Chargily returned an invalid checkout object."
        )

    checkout_id = data.get("id")
    checkout_url = data.get("checkout_url")

    if not isinstance(checkout_id, str) or not checkout_id:
        logger.warning(
            "Chargily checkout response is missing a valid ID."
        )
        raise BillingProviderError(
            "Chargily did not return a checkout ID."
        )

    if not isinstance(checkout_url, str) or not checkout_url:
        logger.warning(
            "Chargily checkout response is missing a valid URL."
        )
        raise BillingProviderError(
            "Chargily did not return a checkout URL."
        )

    parsed = urlparse(checkout_url)
    hostname = (parsed.hostname or "").lower()

    trusted_host = (
        hostname.endswith(".chargily.net")
        or hostname.endswith(".chargily.dz")
    )

    if not trusted_host:
        logger.warning(
            "Chargily checkout URL rejected: hostname=%r",
            hostname,
        )
        raise BillingProviderError(
            "Chargily returned an unexpected checkout URL."
        )

    # Upgrade HTTP to HTTPS only for Chargily's exact payment host.
    if parsed.scheme == "http" and hostname == "pay.chargily.dz":
        parsed = parsed._replace(scheme="https")
        checkout_url = parsed.geturl()

    elif parsed.scheme != "https":
        logger.warning(
            "Chargily checkout URL rejected: scheme=%r hostname=%r",
            parsed.scheme,
            hostname,
        )
        raise BillingProviderError(
            "Chargily returned an unexpected checkout URL."
        )

    return checkout_id, checkout_url
