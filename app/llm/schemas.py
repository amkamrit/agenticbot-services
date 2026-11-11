from typing import Literal

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    message: str


class LLMRequest(BaseModel):
    message: list[LLMMessage] = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, gt=0)


class LLMResponse(BaseModel):
    message: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None


class ContextResolution(BaseModel):
    is_follow_up: bool
    standalone_question: str
    topic: str
