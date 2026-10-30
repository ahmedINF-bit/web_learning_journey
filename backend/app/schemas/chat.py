from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime


class ChatCreate(BaseModel):
    title: Optional[str] = "New Chat"
    folder_id: Optional[int] = None


class ChatUpdate(BaseModel):
    title: Optional[str] = None
    folder_id: Optional[int] = None
    is_pinned: Optional[bool] = None


class ChatResponse(BaseModel):
    id: int
    title: str
    folder_id: Optional[int] = None
    is_pinned: bool
    message_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100000)
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    model: Optional[str] = None
    tokens_used: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatDetailResponse(BaseModel):
    id: int
    title: str
    folder_id: Optional[int] = None
    is_pinned: bool
    messages: list[MessageResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)