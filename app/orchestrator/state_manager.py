import json
import logging

from app.core.redis import redis_client
from app.orchestrator.session_models import SessionState, WorkflowType

logger = logging.getLogger(__name__)


class SessionStateManager:
    STATE_TTL_SECONDS: int = 86400

    @classmethod
    def _get_key(cls, tenant_id: int, conversation_id: str) -> str:
        return f"tenant:{tenant_id}:conversation:{conversation_id}:workflow_state"

    @classmethod
    async def get_state(cls, tenant_id: int, conversation_id: str) -> SessionState:
        key = cls._get_key(tenant_id, conversation_id)
        try:
            raw_data = await redis_client.get(key)
            if raw_data:
                parsed = json.loads(raw_data)
                return SessionState.model_validate(parsed)
        except Exception as exc:
            logger.warning(
                "Failed to retrieve session state from Redis for key %s: %s",
                key,
                exc,
            )
        return SessionState(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            active_workflow=WorkflowType.IDLE,
        )

    @classmethod
    async def save_state(cls, state: SessionState, ttl: int | None = None) -> bool:
        key = cls._get_key(state.tenant_id, state.conversation_id)
        state.touch()
        ttl_val = ttl or cls.STATE_TTL_SECONDS
        try:
            payload = state.model_dump_json()
            await redis_client.set(key, payload, ex=ttl_val)
            return True
        except Exception:
            return False

    @classmethod
    async def set_workflow(
        cls,
        tenant_id: int,
        conversation_id: str,
        workflow: WorkflowType,
        metadata: dict[str, any] | None = None,
    ) -> SessionState:
        state = await cls.get_state(tenant_id, conversation_id)
        state.active_workflow = workflow
        if metadata is not None:
            state.workflow_metadata = metadata
        await cls.save_state(state)
        return state

    @classmethod
    async def update_metadata(
        cls, tenant_id: int, conversation_id: str, updates: dict[str, any]
    ) -> SessionState:
        state = await cls.get_state(tenant_id, conversation_id)
        state.workflow_metadata.update(updates)
        await cls.save_state(state)
        return state

    @classmethod
    async def reset_to_idle(
        cls,
        tenant_id: int,
        conversation_id: str,
    ) -> SessionState:
        state = await cls.get_state(tenant_id, conversation_id)
        state.active_workflow = WorkflowType.IDLE
        state.workflow_metadata.clear()
        state.context_topic = None
        await cls.save_state(state)
        return state

    @classmethod
    async def clear_state(cls, tenant_id: int, conversation_id: str) -> bool:
        key = cls._get_key(tenant_id, conversation_id)
        try:
            await redis_client.delete(key)
            return True
        except Exception as exc:
            logger.error(
                "Failed to delete session state key %s from Redis: %s", key, exc
            )
            return False
