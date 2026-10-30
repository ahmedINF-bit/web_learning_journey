import hashlib
import hmac
import json
from types import SimpleNamespace
from app.api.v1 import billing as billing_module

import pytest
from fastapi import HTTPException

from app.api.v1.billing import create_checkout, chargily_webhook
from app.core.config import settings
from app.schemas.billing import BillingCheckoutRequest


class FakeWebhookRequest:
    def __init__(self, payload: bytes, signature: str | None):
        self.payload = payload
        self.headers = {"signature": signature} if signature else {}

    async def body(self) -> bytes:
        return self.payload


class FakeResult:
    def scalar_one_or_none(self):
        return None


class FakeDB:
    async def execute(self, query):
        return FakeResult()


def sign_payload(payload: bytes, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


@pytest.mark.anyio
async def test_checkout_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ENABLED", False)

    with pytest.raises(HTTPException) as exc:
        await create_checkout(
            BillingCheckoutRequest(plan="pro"),
            user=SimpleNamespace(id=123),
            db=None,
        )

    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", "test-secret")

    request = FakeWebhookRequest(
        b'{"type":"checkout.paid","data":{"id":"checkout_123"}}',
        "invalid-signature",
    )

    with pytest.raises(HTTPException) as exc:
        await chargily_webhook(request, db=None)

    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_webhook_rejects_missing_signature(monkeypatch):
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", "test-secret")

    request = FakeWebhookRequest(
        b'{"type":"checkout.paid","data":{"id":"checkout_123"}}',
        None,
    )

    with pytest.raises(HTTPException) as exc:
        await chargily_webhook(request, db=None)

    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_valid_webhook_for_unknown_checkout_does_not_activate_subscription(
    monkeypatch,
):
    secret = "test-secret"
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", secret)
    monkeypatch.setattr(settings, "CHARGILY_MODE", "test")

    payload = json.dumps({
        "type": "checkout.paid",
        "data": {
            "id": "checkout_not_in_database",
            "status": "paid",
            "amount": 1200,
            "currency": "dzd",
        },
    }).encode("utf-8")

    request = FakeWebhookRequest(payload, sign_payload(payload, secret))

    result = await chargily_webhook(request, db=FakeDB())

    assert result == {"received": True}


@pytest.mark.anyio
async def test_webhook_rejects_mode_mismatch(monkeypatch):
    secret = "test-secret"
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", secret)
    monkeypatch.setattr(settings, "CHARGILY_MODE", "test")

    payload = json.dumps({
        "type": "checkout.paid",
        "livemode": True,
        "data": {"id": "checkout_123"},
    }).encode("utf-8")

    request = FakeWebhookRequest(payload, sign_payload(payload, secret))

    with pytest.raises(HTTPException) as exc:
        await chargily_webhook(request, db=FakeDB())

    assert exc.value.status_code == 400

class BillingSequenceResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class BillingSequenceDB:
    def __init__(self, results):
        self.results = list(results)
        self.execute_calls = 0
        self.commit_calls = 0

    async def execute(self, query):
        self.execute_calls += 1
        return BillingSequenceResult(self.results.pop(0))

    async def commit(self):
        self.commit_calls += 1


@pytest.mark.anyio
async def test_paid_webhook_activates_subscription(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    import hashlib
    import hmac
    import json

    from app.api.v1.billing import chargily_webhook

    secret = "billing-test-secret"
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", secret)
    monkeypatch.setattr(settings, "CHARGILY_MODE", "test")
    monkeypatch.setattr(settings, "BILLING_SUBSCRIPTION_DAYS", 30)
    async def fake_retrieve_chargily_checkout(*, checkout_id: str):
        return {
            "id": checkout_id,
            "status": "paid",
            "amount": 1200,
            "currency": "dzd",
            "livemode": False,
        }

    monkeypatch.setattr(
        billing_module,
        "retrieve_chargily_checkout",
        fake_retrieve_chargily_checkout,
    )
    order = SimpleNamespace(
        id=1,
        user_id=123,
        plan="pro",
        amount_dzd=1200,
        currency="dzd",
        status="pending",
        provider_checkout_id="checkout_paid_123",
        paid_at=None,
    )

    subscription = SimpleNamespace(
        user_id=123,
        plan="free",
        messages_limit=50,
        messages_used=0,
        usage_date=None,
        is_active=True,
        started_at=None,
        expires_at=None,
    )

    db = BillingSequenceDB([order, subscription])

    payload = json.dumps({
        "type": "checkout.paid",
        "data": {
            "id": "checkout_paid_123",
            "status": "paid",
            "amount": 1200,
            "currency": "dzd",
        },
    }).encode()

    signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    response = await chargily_webhook(
        FakeWebhookRequest(payload, signature),
        db,
    )

    assert response == {"received": True}
    assert order.status == "paid"
    assert order.paid_at is not None
    assert subscription.plan == "pro"
    assert subscription.messages_limit == 200
    assert subscription.expires_at > datetime.now(timezone.utc)
    assert db.commit_calls == 1
    async def fake_retrieve_chargily_checkout(*, checkout_id: str):
        return {
            "id": checkout_id,
            "status": "paid",
            "amount": 1200,
            "currency": "dzd",
            "livemode": False,
        }

    monkeypatch.setattr(
        billing_module,
        "retrieve_chargily_checkout",
        fake_retrieve_chargily_checkout,
    )


@pytest.mark.anyio
async def test_paid_webhook_rejects_amount_mismatch(monkeypatch):
    import hashlib
    import hmac
    import json

    from fastapi import HTTPException
    from app.api.v1.billing import chargily_webhook

    secret = "billing-test-secret"
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", secret)
    monkeypatch.setattr(settings, "CHARGILY_MODE", "test")
    async def fake_retrieve_chargily_checkout(*, checkout_id: str):
        return {
            "id": checkout_id,
            "status": "paid",
            "amount": 1,
            "currency": "dzd",
            "livemode": False,
        }

    monkeypatch.setattr(
        billing_module,
        "retrieve_chargily_checkout",
        fake_retrieve_chargily_checkout,
    )
    order = SimpleNamespace(
        id=1,
        user_id=123,
        plan="pro",
        amount_dzd=1200,
        currency="dzd",
        status="pending",
        provider_checkout_id="checkout_amount_123",
        paid_at=None,
    )

    db = BillingSequenceDB([order])

    payload = json.dumps({
        "type": "checkout.paid",
        "data": {
            "id": "checkout_amount_123",
            "status": "paid",
            "amount": 1,
            "currency": "dzd",
        },
    }).encode()

    signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    with pytest.raises(HTTPException) as exc:
        await chargily_webhook(
            FakeWebhookRequest(payload, signature),
            db,
        )

    assert exc.value.status_code == 400
    assert order.status == "pending"
    assert db.commit_calls == 0
    async def fake_retrieve_chargily_checkout(*, checkout_id: str):
        return {
            "id": checkout_id,
            "status": "paid",
            "amount": 1,
            "currency": "dzd",
            "livemode": False,
        }

    monkeypatch.setattr(
        billing_module,
        "retrieve_chargily_checkout",
        fake_retrieve_chargily_checkout,
    )


@pytest.mark.anyio
async def test_duplicate_paid_webhook_does_not_activate_twice(monkeypatch):
    import hashlib
    import hmac
    import json

    from app.api.v1.billing import chargily_webhook

    secret = "billing-test-secret"
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", secret)
    monkeypatch.setattr(settings, "CHARGILY_MODE", "test")

    order = SimpleNamespace(
        id=1,
        user_id=123,
        plan="pro",
        amount_dzd=1200,
        currency="dzd",
        status="paid",
        provider_checkout_id="checkout_duplicate_123",
        paid_at=None,
    )

    db = BillingSequenceDB([order])

    payload = json.dumps({
        "type": "checkout.paid",
        "data": {
            "id": "checkout_duplicate_123",
            "status": "paid",
            "amount": 1200,
            "currency": "dzd",
        },
    }).encode()

    signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    response = await chargily_webhook(
        FakeWebhookRequest(payload, signature),
        db,
    )

    assert response == {"received": True}
    assert order.status == "paid"
    assert db.execute_calls == 1
    assert db.commit_calls == 0
