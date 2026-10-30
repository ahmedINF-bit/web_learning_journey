import hashlib
import hmac

import pytest

from app.core.config import settings
from app.services.billing_service import (
    BillingConfigurationError,
    get_plan_price_dzd,
    verify_chargily_webhook_signature,
)


def test_webhook_signature_accepts_valid_raw_payload(monkeypatch):
    secret = "test-secret"
    payload = b'{"type":"checkout.paid","data":{"id":"checkout_123"}}'
    signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    monkeypatch.setattr(settings, "CHARGILY_API_KEY", secret)

    assert verify_chargily_webhook_signature(payload, signature)


def test_webhook_signature_rejects_tampered_payload(monkeypatch):
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", "test-secret")

    assert not verify_chargily_webhook_signature(
        b'{"type":"checkout.paid"}',
        "invalid-signature",
    )


def test_webhook_signature_rejects_missing_secret(monkeypatch):
    monkeypatch.setattr(settings, "CHARGILY_API_KEY", "")

    assert not verify_chargily_webhook_signature(
        b'{"type":"checkout.paid"}',
        "anything",
    )


def test_pro_price_comes_from_server_configuration(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_PRO_PRICE_DZD", 1200)

    assert get_plan_price_dzd("pro") == 1200


def test_zero_price_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_PRO_PRICE_DZD", 0)

    with pytest.raises(BillingConfigurationError):
        get_plan_price_dzd("pro")


def test_unknown_plan_is_rejected():
    with pytest.raises(BillingConfigurationError):
        get_plan_price_dzd("unknown")
