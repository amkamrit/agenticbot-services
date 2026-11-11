from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    IDLE = "idle"
    RAG = "rag"
    MCP = "mcp"
    FORM_COLLECTION = "form_collection"
    HUMAN_ESCALATION = "human_escalation"


class SessionState(BaseModel):
    tenant_id: int
    conversation_id: str
    active_workflow: WorkflowType = WorkflowType.IDLE
    workflow_metadata: dict[str, Any] = Field(default_factory=dict)
    turn_count: int = 0
    context_topic: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)
        self.turn_count += 1

    def is_in_active_flow(self) -> bool:
        return self.active_workflow in (
            WorkflowType.MCP,
            WorkflowType.FORM_COLLECTION,
            WorkflowType.HUMAN_ESCALATION,
        )


class RoutingDecision(BaseModel):
    workflow: WorkflowType
    state: SessionState
    is_continuation: bool = False
    confidence: float = 1.0
    reason: str = ""
