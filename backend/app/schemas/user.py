from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime


# ========================================================
# REGISTER
# ========================================================

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)


# ========================================================
# LOGIN
# ========================================================

class UserLogin(BaseModel):
    email: str
    password: str


# ========================================================
# USER RESPONSE
# ========================================================

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar: Optional[str] = None
    is_active: bool
    is_admin: bool
    preferred_model: str
    preferred_language: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========================================================
# TOKENS
# ========================================================

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenRefresh(BaseModel):
    refresh_token: str


# ========================================================
# PASSWORD
# ========================================================

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=128,
    )


class ForgotPassword(BaseModel):
    email: str


class ResetPassword(BaseModel):
    token: str
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=128,
    )


# ========================================================
# UPDATE USER
# ========================================================

class UserUpdate(BaseModel):
    username: Optional[str] = None
    avatar: Optional[str] = None
    preferred_model: Optional[str] = None
    preferred_language: Optional[str] = None