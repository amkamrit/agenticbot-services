import asyncio
import json
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.json_utils import safe_parse_json
from app.core.redis import redis_client
from app.llm.factory import create_llm_provider
from app.llm.schemas import LLMMessage, LLMRequest
from app.models.form_collection import FormCollection
from app.orchestrator.session_models import WorkflowType
from app.orchestrator.state_manager import SessionStateManager
from app.services.action_dispatcher import ActionDispatcher

_llm_provider = create_llm_provider(settings)

logger = logging.getLogger(__name__)


# Default fallback if a tenant hasn't configured custom fields yet
DEFAULT_FIELDS = {
    "company_name": "Registered name of your company or business",
    "contact_person": "Full name of the primary contact person",
    "phone": "Contact phone or mobile number",
    "email": "Official business email address",
}


class CollectionService:
    PROGRESS_TTL: int = 86400

    @classmethod
    def _get_progress_key(
        cls, tenant_id: int, conversation_id: str, form_type: str = "default"
    ) -> str:
        return (
            f"tenant_id:{tenant_id}:collection_progress:{conversation_id}:{form_type}"
        )

    @classmethod
    def _get_config_key(cls, tenant_id: int) -> str:
        return f"tenant_id:{tenant_id}_collection_config"

    @classmethod
    async def get_tenant_schema(cls, tenant_id: int) -> dict[str, str]:
        config_key = cls._get_config_key(tenant_id)
        try:
            cached = await redis_client.get(config_key)
            if cached:
                config = json.loads(cached)
                if "fields" in config:
                    return config["fields"]
        except Exception as exc:
            logger.warning(
                "Failed to read collection config for tenant %s: %s",
                tenant_id,
                exc,
            )
        return DEFAULT_FIELDS

    @classmethod
    async def get_tenant_config(cls, tenant_id: int) -> dict[str, any]:
        config_key = cls._get_config_key(tenant_id)
        try:
            cached = await redis_client.get(config_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Redis read error for config key %s: %s", config_key, exc)

        try:
            async with AsyncSessionLocal() as db:
                stmt = select(FormCollection).where(
                    FormCollection.tenant_id == tenant_id,
                    FormCollection.status == "config",
                )
                res = await db.execute(stmt)
                record = res.scalars().first()
                if record and isinstance(record.data, dict):
                    await redis_client.set(
                        config_key, json.dumps(record.data), ex=cls.PROGRESS_TTL
                    )
                    return record.data
        except Exception as exc:
            logger.warning("DB read error for tenant %s config: %s", tenant_id, exc)

        return {"fields": DEFAULT_FIELDS, "action": None}

    @classmethod
    async def process_turn(
        cls, tenant_id: int, conversation_id: str, message: str
    ) -> dict[str, any]:
        progress_key = cls._get_progress_key(tenant_id, conversation_id)
        tenant_config = await cls.get_tenant_config(tenant_id)
        required_fields = tenant_config.get("fields", DEFAULT_FIELDS)
        current_data = await cls._get_current_slots(progress_key)
        extracted = await cls._extract_slots_llm(message, current_data, required_fields)
        action_config = tenant_config.get("action")
        current_data = await cls._get_current_slots(progress_key)
        if extracted:
            current_data.update(extracted)
        missing_fields = [f for f in required_fields if not current_data.get(f)]
        if not missing_fields:
            await cls._persist_completed_collection(tenant_id, current_data)
            await cls._clear_progress(progress_key)
            await SessionStateManager.reset_to_idle(tenant_id, conversation_id)

            if action_config:
                asyncio.create_task(
                    ActionDispatcher.dispatch_action(
                        tenant_id=tenant_id,
                        action_config=action_config,
                        collected_data=current_data,
                    )
                )
            summary_lines = "\n".join(
                f"• {k.replace('_', ' ').title()}: {v}" for k, v in current_data.items()
            )
            return {
                "id": conversation_id,
                "message": (
                    f"Thank you! Your information has been successfully recorded:\n"
                    f"{summary_lines}\n\n"
                    f"Is there anything else I can help you with today?"
                ),
                "workflow": "form_collection",
                "status": "completed",
                "data": current_data,
            }
        await cls._save_progress(progress_key, current_data)
        await SessionStateManager.set_workflow(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            workflow=WorkflowType.FORM_COLLECTION,
            metadata={"missing_fields": missing_fields},
        )
        next_field = missing_fields[0]
        field_desc = required_fields.get(
            next_field, next_field.replace("_", "").title()
        )
        return {
            "id": conversation_id,
            "message": f"Could you please provide your {field_desc}?",
            "workflow": "form_collection",
            "status": "in_progress",
            "collected": current_data,
            "next_field": next_field,
        }

    @classmethod
    async def _get_current_slots(cls, key: str) -> dict[str, any]:
        try:
            cached = await redis_client.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        return {}

    @classmethod
    async def _save_progress(cls, key: str, data: dict[str, any]) -> None:
        try:
            await redis_client.set(key, json.dumps(data), ex=cls.PROGRESS_TTL)
        except Exception:
            pass

    @classmethod
    async def _clear_progress(cls, key: str) -> None:
        try:
            await redis_client.delete(key)
        except Exception:
            pass

    @classmethod
    async def _persist_completed_collection(
        cls, tenant_id: int, data: dict[str, any]
    ) -> None:
        try:
            async with AsyncSessionLocal() as db:
                record = FormCollection(
                    tenant_id=tenant_id, data=data, status="completed"
                )
                db.add(record)
                await db.commit()
        except Exception:
            logger.exception("Failed to persist collection for tenant_id=%s", tenant_id)

    @classmethod
    async def _extract_slots_llm(
        cls,
        message: str,
        existing_data: dict[str, any],
        required_fields: dict[str, str],
    ) -> dict[str, any]:
        prompt = f"""You are a data extraction system.
Extract any values for these target fields mentioned by the user:
Target Fields and descriptions:
{json.dumps(required_fields, indent=2)}

Already Collected so far:
{json.dumps(existing_data, indent=2)}

User Input:
"{message}"

Return ONLY valid JSON with any newly provided or updated fields:
{{
    "field_name": "extracted_value"
}}
If a field was not mentioned in the input, omit it.
"""
        try:
            req = LLMRequest(
                message=[LLMMessage(role="user", message=prompt)],
                temperature=0.0,
                max_output_tokens=150,
            )
            resp = await _llm_provider.generate(req)
            if resp and resp.message:
                parsed = safe_parse_json(resp.message)
                if isinstance(parsed, dict):
                    return {k: v for k, v in parsed.items() if v and v != "..."}

        except Exception as exc:
            logger.warning("Slot extraction error: %s", exc)

        return {}
