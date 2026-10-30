from unittest.mock import Mock

import pytest

import app.core.email as email_service
from app.core.config import settings


# ========================================================
# EMAIL CONFIGURATION
# ========================================================

def configure_test_smtp(monkeypatch):
    monkeypatch.setattr(
        settings,
        "SMTP_HOST",
        "smtp.example.com",
    )
    monkeypatch.setattr(
        settings,
        "SMTP_PORT",
        587,
    )
    monkeypatch.setattr(
        settings,
        "SMTP_USER",
        "mailer@example.com",
    )
    monkeypatch.setattr(
        settings,
        "SMTP_PASSWORD",
        "test-password",
    )
    monkeypatch.setattr(
        settings,
        "FRONTEND_URL",
        "http://localhost:5173",
    )


# ========================================================
# PASSWORD RESET EMAIL
# ========================================================

def test_send_password_reset_email_builds_and_sends_message(
    monkeypatch,
):
    configure_test_smtp(monkeypatch)

    smtp_server = Mock()
    smtp_factory = Mock(return_value=smtp_server)

    # Mock the SMTP context manager so no real connection is made.
    smtp_server.__enter__ = Mock(return_value=smtp_server)
    smtp_server.__exit__ = Mock(return_value=False)

    monkeypatch.setattr(
        email_service.smtplib,
        "SMTP",
        smtp_factory,
    )

    email_service.send_password_reset_email(
        to_email="student@example.com",
        token="test-reset-token",
    )

    smtp_factory.assert_called_once_with(
        "smtp.example.com",
        587,
        timeout=10,
    )

    smtp_server.starttls.assert_called_once()
    smtp_server.login.assert_called_once_with(
        "mailer@example.com",
        "test-password",
    )
    smtp_server.send_message.assert_called_once()

    message = smtp_server.send_message.call_args.args[0]

    assert message["To"] == "student@example.com"
    assert message["From"] == "mailer@example.com"
    assert message["Subject"] == (
        "Talaba AI - Password Reset"
    )

    body = message.get_content()

    assert (
        "http://localhost:5173/reset-password?"
        "token=test-reset-token"
    ) in body
    assert "expires in 30 minutes" in body


def test_send_password_reset_email_rejects_missing_smtp_config(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "SMTP_HOST",
        None,
    )

    smtp_factory = Mock()

    monkeypatch.setattr(
        email_service.smtplib,
        "SMTP",
        smtp_factory,
    )

    with pytest.raises(
        RuntimeError,
        match="SMTP is not configured",
    ):
        email_service.send_password_reset_email(
            to_email="student@example.com",
            token="test-reset-token",
        )

    smtp_factory.assert_not_called()