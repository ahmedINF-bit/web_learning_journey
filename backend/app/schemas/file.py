from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from typing import Optional, Literal

class FileResponse(BaseModel):
    id: int
    filename: str
    original_name: str
    file_type: str
    file_size: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileAsk(BaseModel):
    question: str
    file_id: int


class AIRequest(BaseModel):
    prompt: str
    system_prompt: Optional[str] = None
    model: Optional[str] = "gpt-4o-mini"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048


class AIResponse(BaseModel):
    content: str
    model: str
    tokens_used: int

class FileStudyToolRequest(BaseModel):
    file_id: int
    tool: Literal["summarize", "quiz", "flashcards", "solve-math"]
