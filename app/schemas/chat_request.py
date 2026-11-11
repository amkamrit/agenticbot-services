from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=500)
    id: str = Field(min_length=5, max_length=50)
    tenant_id: int = Field(ge=0)
