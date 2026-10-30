from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = "#3B82F6"


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class FolderResponse(BaseModel):
    id: int
    name: str
    color: str
    chat_count: int = 0
    note_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)