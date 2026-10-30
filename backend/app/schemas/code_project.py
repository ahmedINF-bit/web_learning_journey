from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CodeLanguage = Literal["c", "python", "javascript"]
MAX_CODE_LENGTH = 200_000


class CodeProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    language: CodeLanguage
    code: str = Field(..., max_length=MAX_CODE_LENGTH)
    folder_id: int

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("File name cannot be empty.")
        return value


class CodeProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    language: CodeLanguage | None = None
    code: str | None = Field(default=None, max_length=MAX_CODE_LENGTH)
    folder_id: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("File name cannot be empty.")
        return value


class CodeProjectResponse(BaseModel):
    id: int
    user_id: int
    folder_id: int | None = None
    name: str
    language: str
    code: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
