from typing import Literal

from pydantic import BaseModel, Field


class ResolutionResult(BaseModel):
    status: Literal["active", "resolved", "pending", "escalated"]

    reason: str = Field(description="Short explanation for the resolution decision.")

    confidence: float = Field(
        ge=0, le=1, description="Confidence in the resolution decision."
    )
