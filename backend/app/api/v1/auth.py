import asyncio
import hashlib
import logging
import secrets

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.email import send_password_reset_email
from app.core.rate_limit import limiter
from app.core.security import (
    hash_password,
    verify_password,
    create_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.models.user import User
from app.models.settings import UserSettings
from app.models.subscription import Subscription
from app.models.password_reset_token import PasswordResetToken
from app.schemas.user import (
    UserRegister,
    UserResponse,
    TokenResponse,
    TokenRefresh,
    PasswordChange,
    UserUpdate,
    ForgotPassword,
    ResetPassword,
)


logger = logging.getLogger(__name__)

PASSWORD_RESET_RESPONSE = {
    "message": "If the email exists, a reset link has been sent"
}

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ========================================================
# REGISTER
# ========================================================

@router.post("/register", response_model=TokenResponse)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(User).where(
            (User.email == data.email)
            | (User.username == data.username)
        )
    )

    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="User with this email or username already exists",
        )

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )

    db.add(user)
    await db.flush()

    user_settings = UserSettings(user_id=user.id)
    subscription = Subscription(user_id=user.id)

    db.add(user_settings)
    db.add(subscription)

    await db.flush()

    access_token = create_token({"sub": str(user.id)})
    refresh_token_value = create_refresh_token(
        {"sub": str(user.id)}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_value,
        user=UserResponse.model_validate(user),
    )


# ========================================================
# LOGIN
# ========================================================

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.email == form_data.username)
    )

    user = result.scalar_one_or_none()

    if (
        not user
        or not verify_password(
            form_data.password,
            user.hashed_password,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token = create_token({"sub": str(user.id)})
    refresh_token_value = create_refresh_token(
        {"sub": str(user.id)}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_value,
        user=UserResponse.model_validate(user),
    )


# ========================================================
# REFRESH TOKEN
# ========================================================

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: TokenRefresh,
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(data.refresh_token)

    if payload.get("token_type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")

    try:
        user_id = int(user_id)

        if user_id <= 0:
            raise ValueError

    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    result = await db.execute(
        select(User).where(User.id == user_id)
    )

    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token = create_token({"sub": str(user.id)})
    refresh_token_value = create_refresh_token(
        {"sub": str(user.id)}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_value,
        user=UserResponse.model_validate(user),
    )


# ========================================================
# CURRENT USER
# ========================================================

@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
):
    return UserResponse.model_validate(user)


# ========================================================
# UPDATE CURRENT USER
# ========================================================

@router.put("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.username:
        existing = await db.execute(
            select(User).where(
                User.username == data.username,
                User.id != user.id,
            )
        )

        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Username already taken",
            )

        user.username = data.username

    if data.avatar is not None:
        user.avatar = data.avatar

    if data.preferred_model:
        user.preferred_model = data.preferred_model

    if data.preferred_language:
        user.preferred_language = data.preferred_language

    await db.flush()

    return UserResponse.model_validate(user)


# ========================================================
# CHANGE PASSWORD
# ========================================================

@router.post("/change-password")
async def change_password(
    data: PasswordChange,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(
        data.current_password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.hashed_password = hash_password(data.new_password)

    await db.flush()

    return {"message": "Password changed successfully"}


# ========================================================
# FORGOT PASSWORD - INTERNAL LOGIC
# ========================================================

async def forgot_password(
    data: ForgotPassword,
    db: AsyncSession,
):
    result = await db.execute(
        select(User).where(User.email == data.email)
    )

    user = result.scalar_one_or_none()

    # Don't reveal whether the email belongs to an account.
    if user is None or not user.is_active:
        return PASSWORD_RESET_RESPONSE.copy()

    previous_result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )

    previous_tokens = previous_result.scalars().all()

    raw_token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(minutes=30)
        ),
    )

    db.add(reset_token)
    await db.flush()

    try:
        # SMTP is blocking I/O, so keep it off the event loop.
        await asyncio.to_thread(
            send_password_reset_email,
            user.email,
            raw_token,
        )

    except Exception:
        logger.exception("Password reset email delivery failed")

        await db.delete(reset_token)
        await db.flush()

        return PASSWORD_RESET_RESPONSE.copy()

    now = datetime.now(timezone.utc)

    for previous_token in previous_tokens:
        previous_token.used_at = now

    return PASSWORD_RESET_RESPONSE.copy()


# ========================================================
# FORGOT PASSWORD - API ENDPOINT
# ========================================================

@router.post(
    "/forgot-password",
    name="forgot_password_endpoint",
)
@limiter.limit(settings.PASSWORD_RESET_RATE_LIMIT)
async def forgot_password_endpoint(
    request: Request,
    data: ForgotPassword,
    db: AsyncSession = Depends(get_db),
):
    return await forgot_password(
        data=data,
        db=db,
    )


# ========================================================
# RESET PASSWORD
# ========================================================

@router.post("/reset-password")
async def reset_password(
    data: ResetPassword,
    db: AsyncSession = Depends(get_db),
):
    token_hash = hashlib.sha256(
        data.token.encode("utf-8")
    ).hexdigest()

    result = await db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash)
        .with_for_update()
    )

    reset_token = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    invalid_message = "Invalid or expired reset token"

    if reset_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=invalid_message,
        )

    if reset_token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=invalid_message,
        )

    expires_at = reset_token.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=invalid_message,
        )

    user_result = await db.execute(
        select(User).where(User.id == reset_token.user_id)
    )

    user = user_result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=invalid_message,
        )

    user.hashed_password = hash_password(data.new_password)
    reset_token.used_at = now

    # Invalidate all other unused reset tokens for this user.
    other_result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != reset_token.id,
            PasswordResetToken.used_at.is_(None),
        )
    )

    for other_token in other_result.scalars().all():
        other_token.used_at = now

    await db.flush()

    return {
        "message": "Password has been reset successfully"
    }