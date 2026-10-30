from pydantic import BaseModel, ConfigDict, Field


class MemoryResponse(BaseModel):
    id: int
    memory_type: str
    content: str

    model_config = ConfigDict(from_attributes=True)


class MemoryUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)