import logging

from app.core.database import AsyncSessionLocal
from app.repositories.chat_repository import ChatRepository

logger = logging.getLogger(__name__)


async def save_message_to_db(
    conversation_id: str, role: str, content: str, tenant_id: int
):
    try:
        async with AsyncSessionLocal() as db:
            await ChatRepository.create_conversation(
                db=db,
                conversation_id=conversation_id,
                role=role,
                content=content,
                tenant_id=tenant_id,
            )

    except Exception:
        logger.exception(
            "Failed to persist chat message for conversation_id=%s",
            conversation_id,
        )
