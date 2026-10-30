from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

import app.api.v1.auth as auth
from app.core.security import decode_token
from app.models.user import User
from app.models.settings import UserSettings
from app.models.subscription import Subscription
from app.schemas.user import UserRegister


def make_active_user():
    return SimpleNamespace(
        id=3,
        username="test_user",
        email="test@example.com",
        hashed_password="hashed-password",
        avatar=None,
        is_active=True,
        is_admin=False,
        preferred_model="gpt-4o-mini",
        preferred_language="fr",
        created_at=datetime.now(timezone.utc),
    )


# ========================================================
# REGISTER
# ========================================================

@pytest.mark.anyio
async def test_register_creates_user_settings_and_subscription(monkeypatch):
    db = AsyncMock()
    added_objects = []

    # db.add() is synchronous, unlike execute() and flush().
    db.add = Mock(side_effect=added_objects.append)

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: None
    )

    monkeypatch.setattr(
        auth,
        "hash_password",
        lambda password: "hashed-password",
    )

    async def flush_side_effect():
        # Simulate the ID and database-generated fields assigned
        # after the first database flush.
        user = added_objects[0]

        if isinstance(user, User) and user.id is None:
            user.id = 3
            user.is_active = True
            user.is_admin = False
            user.avatar = None
            user.preferred_model = "gpt-4o-mini"
            user.preferred_language = "en"
            user.created_at = datetime.now(timezone.utc)

    db.flush.side_effect = flush_side_effect

    data = UserRegister(
        username="test_user",
        email="test@example.com",
        password="StrongPass123",
    )

    response = await auth.register(data=data, db=db)

    assert response.user.id == 3
    assert response.user.username == "test_user"
    assert response.user.email == "test@example.com"
    assert added_objects[0].hashed_password == "hashed-password"

    assert len(added_objects) == 3
    assert isinstance(added_objects[0], User)
    assert isinstance(added_objects[1], UserSettings)
    assert isinstance(added_objects[2], Subscription)

    assert added_objects[1].user_id == 3
    assert added_objects[2].user_id == 3
    assert db.flush.await_count == 2

    access_payload = decode_token(response.access_token)
    refresh_payload = decode_token(response.refresh_token)

    assert access_payload["token_type"] == "access"
    assert refresh_payload["token_type"] == "refresh"
    assert access_payload["sub"] == "3"
    assert refresh_payload["sub"] == "3"


@pytest.mark.anyio
async def test_register_rejects_existing_user():
    db = AsyncMock()

    existing_user = SimpleNamespace(id=99)

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: existing_user
    )

    data = UserRegister(
        username="existing_user",
        email="existing@example.com",
        password="StrongPass123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth.register(data=data, db=db)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "User with this email or username already exists"
    )

    db.add.assert_not_called()
    db.flush.assert_not_awaited()


# ========================================================
# LOGIN
# ========================================================

@pytest.mark.anyio
async def test_login_returns_tokens_for_valid_credentials(monkeypatch):
    db = AsyncMock()
    active_user = make_active_user()

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: active_user
    )

    verify_password = Mock(return_value=True)
    monkeypatch.setattr(auth, "verify_password", verify_password)

    form_data = SimpleNamespace(
        username="test@example.com",
        password="StrongPass123",
    )

    response = await auth.login(form_data=form_data, db=db)

    verify_password.assert_called_once_with(
        "StrongPass123",
        "hashed-password",
    )

    assert response.user.id == 3
    assert response.user.email == "test@example.com"
    assert response.access_token
    assert response.refresh_token

    access_payload = decode_token(response.access_token)
    refresh_payload = decode_token(response.refresh_token)

    assert access_payload["token_type"] == "access"
    assert refresh_payload["token_type"] == "refresh"
    assert access_payload["sub"] == "3"
    assert refresh_payload["sub"] == "3"


@pytest.mark.anyio
async def test_login_rejects_invalid_credentials(monkeypatch):
    db = AsyncMock()
    active_user = make_active_user()

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: active_user
    )

    monkeypatch.setattr(
        auth,
        "verify_password",
        lambda password, hashed_password: False,
    )

    form_data = SimpleNamespace(
        username="test@example.com",
        password="WrongPassword123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth.login(form_data=form_data, db=db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid credentials"


@pytest.mark.anyio
async def test_login_rejects_unknown_email():
    db = AsyncMock()

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: None
    )

    form_data = SimpleNamespace(
        username="unknown@example.com",
        password="StrongPass123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth.login(form_data=form_data, db=db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid credentials"


@pytest.mark.anyio
async def test_login_rejects_inactive_user(monkeypatch):
    db = AsyncMock()
    inactive_user = make_active_user()
    inactive_user.is_active = False

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: inactive_user
    )

    monkeypatch.setattr(
        auth,
        "verify_password",
        lambda password, hashed_password: True,
    )

    form_data = SimpleNamespace(
        username="test@example.com",
        password="StrongPass123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth.login(form_data=form_data, db=db)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Account is deactivated"