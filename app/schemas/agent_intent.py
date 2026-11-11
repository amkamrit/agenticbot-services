from typing import Literal

from pydantic import BaseModel, Field


class AgentIntentResult(BaseModel):
    wants_agent: bool
    intent: Literal[
        "request_agent",
        "continue_ai",
        "uncertain",
    ]
    reason: str = Field(description="Short explanation for the decision.")
    confidence: float = Field(ge=0, le=1)
