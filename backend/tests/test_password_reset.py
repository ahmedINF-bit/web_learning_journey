import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

import app.api.v1.auth as auth
from app.models.password_reset_token import PasswordResetToken
from app.schemas.user import ForgotPassword, ResetPassword


def make_result(value=None, rows=None):
    return SimpleNamespace(
        scalar_one_or_none=lambda: value,
        scalars=lambda: SimpleNamespace(
            all=lambda: rows if rows is not None else []
        ),
    )


def make_user(is_active=True):
    return SimpleNamespace(
        id=3,
        email="test@example.com",
        is_active=is_active,
        hashed_password="old-hash",
    )


def make_reset_token(
    raw_token="valid-reset-token",
    token_id=1,
    expires_at=None,
    used_at=None,
):
    return PasswordResetToken(
        id=token_id,
        user_id=3,
        token_hash=hashlib.sha256(
            raw_token.encode("utf-8")
        ).hexdigest(),
        expires_at=(
            expires_at
            or datetime.now(timezone.utc)
            + timedelta(minutes=30)
        ),
        used_at=used_at,
    )


# ========================================================
# FORGOT PASSWORD
# ========================================================

@pytest.mark.anyio
async def test_forgot_password_unknown_email_returns_generic_message():
    db = AsyncMock()
    db.add = Mock()

    db.execute.return_value = make_result(None)

    response = await auth.forgot_password(
        data=ForgotPassword(email="unknown@example.com"),
        db=db,
    )

    assert response == auth.PASSWORD_RESET_RESPONSE
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_forgot_password_creates_hashed_token(monkeypatch):
    db = AsyncMock()

    user = make_user()
    previous_token = make_reset_token(
        raw_token="previous-token"
    )

    db.execute.side_effect = [
        make_result(user),
        make_result(rows=[previous_token]),
    ]

    added_objects = []
    db.add = Mock(side_effect=added_objects.append)

    send_email_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        auth.asyncio,
        "to_thread",
        send_email_mock,
    )

    response = await auth.forgot_password(
        data=ForgotPassword(email=user.email),
        db=db,
    )

    assert response == auth.PASSWORD_RESET_RESPONSE
    assert len(added_objects) == 1

    reset_token = added_objects[0]
    assert isinstance(reset_token, PasswordResetToken)
    assert reset_token.user_id == user.id
    assert reset_token.used_at is None

    # The raw token must not be stored in the database.
    raw_token = send_email_mock.await_args.args[2]
    expected_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    assert reset_token.token_hash == expected_hash
    assert reset_token.token_hash != raw_token

    assert reset_token.expires_at > datetime.now(timezone.utc)
    assert previous_token.used_at is not None

    send_email_mock.assert_awaited_once()
    db.flush.assert_awaited_once()


@pytest.mark.anyio
async def test_forgot_password_email_failure_removes_new_token(
    monkeypatch,
):
    db = AsyncMock()
    user = make_user()

    db.execute.side_effect = [
        make_result(user),
        make_result(rows=[]),
    ]

    added_objects = []
    db.add = Mock(side_effect=added_objects.append)

    send_email_mock = AsyncMock(
        side_effect=RuntimeError("SMTP unavailable")
    )
    monkeypatch.setattr(
        auth.asyncio,
        "to_thread",
        send_email_mock,
    )

    response = await auth.forgot_password(
        data=ForgotPassword(email=user.email),
        db=db,
    )

    assert response == auth.PASSWORD_RESET_RESPONSE

    reset_token = added_objects[0]
    db.delete.assert_awaited_once_with(reset_token)
    assert db.flush.await_count == 2


# ========================================================
# RESET PASSWORD
# ========================================================

@pytest.mark.anyio
async def test_reset_password_updates_password_and_invalidates_tokens(
    monkeypatch,
):
    db = AsyncMock()

    raw_token = "valid-reset-token"
    reset_token = make_reset_token(raw_token=raw_token)

    other_token = make_reset_token(
        raw_token="another-reset-token",
        token_id=2,
    )

    user = make_user()

    db.execute.side_effect = [
        make_result(reset_token),
        make_result(user),
        make_result(rows=[other_token]),
    ]

    monkeypatch.setattr(
        auth,
        "hash_password",
        lambda password: "new-hashed-password",
    )

    response = await auth.reset_password(
        data=ResetPassword(
            token=raw_token,
            new_password="NewStrongPass123",
        ),
        db=db,
    )

    assert response["message"] == (
        "Password has been reset successfully"
    )
    assert user.hashed_password == "new-hashed-password"
    assert reset_token.used_at is not None
    assert other_token.used_at is not None
    db.flush.assert_awaited_once()


@pytest.mark.anyio
async def test_reset_password_rejects_unknown_token():
    db = AsyncMock()
    db.execute.return_value = make_result(None)

    with pytest.raises(HTTPException) as exc_info:
        await auth.reset_password(
            data=ResetPassword(
                token="unknown-token",
                new_password="NewStrongPass123",
            ),
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid or expired reset token"
    assert db.execute.await_count == 1
    db.flush.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("state", ["expired", "used"])
async def test_reset_password_rejects_expired_or_used_token(state):
    db = AsyncMock()
    now = datetime.now(timezone.utc)

    if state == "expired":
        reset_token = make_reset_token(
            expires_at=now - timedelta(minutes=1)
        )
    else:
        reset_token = make_reset_token(used_at=now)

    db.execute.return_value = make_result(reset_token)

    with pytest.raises(HTTPException) as exc_info:
        await auth.reset_password(
            data=ResetPassword(
                token="valid-reset-token",
                new_password="NewStrongPass123",
            ),
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid or expired reset token"
    assert db.execute.await_count == 1
    db.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_reset_password_rejects_inactive_user(monkeypatch):
    db = AsyncMock()

    reset_token = make_reset_token()
    inactive_user = make_user(is_active=False)

    db.execute.side_effect = [
        make_result(reset_token),
        make_result(inactive_user),
    ]

    monkeypatch.setattr(
        auth,
        "hash_password",
        lambda password: "new-hashed-password",
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth.reset_password(
            data=ResetPassword(
                token="valid-reset-token",
                new_password="NewStrongPass123",
            ),
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid or expired reset token"
    assert inactive_user.hashed_password == "old-hash"
    db.flush.assert_not_awaited()