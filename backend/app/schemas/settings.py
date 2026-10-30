from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class SettingsUpdate(BaseModel):
    theme: Optional[str] = None
    language: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    notifications_enabled: Optional[bool] = None


class SettingsResponse(BaseModel):
    theme: str
    language: str
    temperature: float
    max_tokens: int
    system_prompt: str
    notifications_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionResponse(BaseModel):
    plan: str
    messages_used: int
    messages_limit: int
    is_active: bool
    started_at: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class APIKeyUpdate(BaseModel):
    api_key: str


class AdminStats(BaseModel):
    total_users: int
    total_chats: int
    total_messages: int
    total_files: int
    active_users_today: int
    messages_today: int