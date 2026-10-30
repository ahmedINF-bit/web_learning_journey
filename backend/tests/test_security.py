from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from jose import jwt

from app.api.v1.auth import refresh_token
from app.core.config import settings
from app.core.security import (
    create_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.schemas.user import TokenRefresh


# ========================================================
# DECODE TOKEN
# ========================================================

def test_decode_invalid_token_returns_401():
    with pytest.raises(HTTPException) as exc_info:
        decode_token("this-is-not-a-valid-jwt")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


# ========================================================
# GET CURRENT USER
# ========================================================

@pytest.mark.anyio
async def test_get_current_user_missing_sub_returns_401():
    token = jwt.encode(
        {},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            token=token,
            db=db,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


@pytest.mark.anyio
async def test_get_current_user_invalid_sub_returns_401():
    token = create_token({"sub": "abc"})
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            token=token,
            db=db,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


@pytest.mark.anyio
async def test_get_current_user_user_not_found_returns_401():
    token = create_token({"sub": "999999999"})
    db = AsyncMock()

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: None
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            token=token,
            db=db,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User not found"


@pytest.mark.anyio
async def test_get_current_user_inactive_user_returns_403():
    token = create_token({"sub": "3"})

    inactive_user = SimpleNamespace(
        id=3,
        is_active=False,
    )

    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: inactive_user
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            token=token,
            db=db,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "User is inactive"


@pytest.mark.anyio
async def test_get_current_user_returns_active_user():
    token = create_token({"sub": "3"})

    active_user = SimpleNamespace(
        id=3,
        is_active=True,
    )

    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: active_user
    )

    user = await get_current_user(
        token=token,
        db=db,
    )

    assert user is active_user


# ========================================================
# TOKEN TYPE VALIDATION
# ========================================================

def test_create_token_has_access_type():
    token = create_token({"sub": "3"})
    payload = decode_token(token)

    assert payload.get("token_type") == "access"


def test_create_refresh_token_has_refresh_type():
    token = create_refresh_token({"sub": "3"})
    payload = decode_token(token)

    assert payload.get("token_type") == "refresh"


@pytest.mark.anyio
async def test_get_current_user_rejects_refresh_token():
    token = create_refresh_token({"sub": "3"})
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            token=token,
            db=db,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"
    db.execute.assert_not_awaited()


# ========================================================
# REFRESH ENDPOINT TESTS
# ========================================================

@pytest.mark.anyio
async def test_refresh_rejects_access_token():
    db = AsyncMock()

    data = TokenRefresh(
        refresh_token=create_token({"sub": "3"})
    )

    with pytest.raises(HTTPException) as exc_info:
        await refresh_token(data=data, db=db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid refresh token"
    db.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_refresh_rejects_invalid_user_id():
    db = AsyncMock()

    data = TokenRefresh(
        refresh_token=create_refresh_token({"sub": "abc"})
    )

    with pytest.raises(HTTPException) as exc_info:
        await refresh_token(data=data, db=db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid refresh token"
    db.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_refresh_rejects_missing_user():
    db = AsyncMock()

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: None
    )

    data = TokenRefresh(
        refresh_token=create_refresh_token({"sub": "999999999"})
    )

    with pytest.raises(HTTPException) as exc_info:
        await refresh_token(data=data, db=db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User not found"


@pytest.mark.anyio
async def test_refresh_rejects_inactive_user():
    db = AsyncMock()

    inactive_user = SimpleNamespace(
        id=3,
        is_active=False,
    )

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: inactive_user
    )

    data = TokenRefresh(
        refresh_token=create_refresh_token({"sub": "3"})
    )

    with pytest.raises(HTTPException) as exc_info:
        await refresh_token(data=data, db=db)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Account is deactivated"


@pytest.mark.anyio
async def test_refresh_returns_new_tokens_for_active_user():
    db = AsyncMock()

    active_user = SimpleNamespace(
        id=3,
        is_active=True,
        is_admin=False,
        username="test_user",
        email="test@example.com",
        avatar=None,
        preferred_model="gpt-4o-mini",
        preferred_language="fr",
        created_at=datetime.now(timezone.utc),
    )

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: active_user
    )

    data = TokenRefresh(
        refresh_token=create_refresh_token({"sub": "3"})
    )
    original_refresh_token = data.refresh_token

    response = await refresh_token(data=data, db=db)

    assert response.refresh_token != original_refresh_token
    assert response.access_token
    assert response.refresh_token
    assert response.user.id == 3

    access_payload = decode_token(response.access_token)
    refresh_payload = decode_token(response.refresh_token)

    assert access_payload["token_type"] == "access"
    assert refresh_payload["token_type"] == "refresh"
    assert access_payload["sub"] == "3"
    assert refresh_payload["sub"] == "3"
