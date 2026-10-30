from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

import app.api.v1.auth as auth
from app.schemas.user import PasswordChange


@pytest.mark.anyio
async def test_change_password_rejects_incorrect_current_password(
    monkeypatch,
):
    db = AsyncMock()
    user = SimpleNamespace(
        id=3,
        hashed_password="stored-hash",
    )

    verify_mock = Mock(return_value=False)
    hash_mock = Mock(return_value="new-hash")

    monkeypatch.setattr(auth, "verify_password", verify_mock)
    monkeypatch.setattr(auth, "hash_password", hash_mock)

    data = PasswordChange(
        current_password="WrongPassword123",
        new_password="NewPassword123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth.change_password(
            data=data,
            user=user,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Current password is incorrect"
    verify_mock.assert_called_once_with(
        "WrongPassword123",
        "stored-hash",
    )
    hash_mock.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_change_password_updates_hashed_password(
    monkeypatch,
):
    db = AsyncMock()
    user = SimpleNamespace(
        id=3,
        hashed_password="old-hash",
    )

    verify_mock = Mock(return_value=True)
    hash_mock = Mock(return_value="new-hash")

    monkeypatch.setattr(auth, "verify_password", verify_mock)
    monkeypatch.setattr(auth, "hash_password", hash_mock)

    data = PasswordChange(
        current_password="CurrentPassword123",
        new_password="NewPassword123",
    )

    response = await auth.change_password(
        data=data,
        user=user,
        db=db,
    )

    assert response["message"] == "Password changed successfully"
    assert user.hashed_password == "new-hash"

    verify_mock.assert_called_once_with(
        "CurrentPassword123",
        "old-hash",
    )
    hash_mock.assert_called_once_with("NewPassword123")
    db.flush.assert_awaited_once()