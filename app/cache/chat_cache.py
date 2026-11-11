import json
import logging

from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client
from app.repositories.chat_repository import ChatRepository

logger = logging.getLogger(__name__)


class ChatCache:
    CACHE_TTL = 86400

    @staticmethod
    async def get_conversation(conversation_id: str, tenant_id: int):
        cache_key = f"tenant:{tenant_id}:conversation:{conversation_id}"
        cached_messages = await redis_client.get(cache_key)
        if cached_messages is not None:
            try:
                return json.loads(cached_messages)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Invalid Redis conversation data",
                    extra={
                        "tenant_id": tenant_id,
                        "conversation_id": conversation_id,
                    },
                )
                await redis_client.delete(cache_key)

        async with AsyncSessionLocal() as db:
            messages = await ChatRepository.get_conversation(
                db=db, conversation_id=conversation_id, tenant_id=tenant_id
            )
            # Convert SQLAlchemy objects into dictionaries
        formatted_messages = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ]

        # Fallback to PostgreSQL
        await redis_client.set(
            cache_key, json.dumps(formatted_messages), ex=ChatCache.CACHE_TTL
        )
        return formatted_messages

    @staticmethod
    async def save_conversation(
        conversation_id: str, tenant_id: int, messages: list, is_new: bool = False
    ):
        cache_key = f"tenant:{tenant_id}:conversation:{conversation_id}"

        if is_new:
            existing_messages = []
        else:
            cached_messages = await redis_client.get(cache_key)
            if cached_messages is not None:
                try:
                    existing_messages = json.loads(cached_messages)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "Invalid Redis conversation data during save",
                        extra={
                            "tenant_id": tenant_id,
                            "conversation_id": conversation_id,
                        },
                    )
                    await redis_client.delete(cache_key)
                    existing_messages = await ChatCache.get_conversation(
                        conversation_id=conversation_id, tenant_id=tenant_id
                    )
            else:
                existing_messages = await ChatCache.get_conversation(
                    conversation_id=conversation_id, tenant_id=tenant_id
                )
        updated_messages = existing_messages + messages

        await redis_client.set(
            cache_key, json.dumps(updated_messages), ex=ChatCache.CACHE_TTL
        )
        return updated_messages
