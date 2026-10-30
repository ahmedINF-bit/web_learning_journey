from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CodeFileLanguage = Literal["c", "python", "javascript"]
MAX_CODE_FILE_LENGTH = 200_000


class CodeFileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    language: CodeFileLanguage
    code: str = Field(default="", max_length=MAX_CODE_FILE_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("File name cannot be empty.")
        if any(char in value for char in ("/", "\\", "\x00")) or value.endswith("."):
            raise ValueError("Enter a valid file name without a path.")
        return value


class CodeFileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    language: CodeFileLanguage | None = None
    code: str | None = Field(default=None, max_length=MAX_CODE_FILE_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("File name cannot be empty.")
        if any(char in value for char in ("/", "\\", "\x00")) or value.endswith("."):
            raise ValueError("Enter a valid file name without a path.")
        return value


class CodeFileResponse(BaseModel):
    id: int
    project_id: int
    name: str
    language: str
    code: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
