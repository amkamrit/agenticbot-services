from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.message import Message


class ChatRepository:
    @staticmethod
    async def get_conversation(
        db: AsyncSession, conversation_id: str, tenant_id: int
    ) -> list[Message] | None:
        result = await db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.conversation_id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            return []

        return sorted(conversation.messages, key=lambda m: m.created_at)

    @staticmethod
    async def create_conversation(
        db: AsyncSession, conversation_id: str, role: str, content: str, tenant_id: int
    ) -> Message:
        try:
            result = await db.execute(
                select(Conversation).where(
                    Conversation.conversation_id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation is None:
                conversation = Conversation(
                    conversation_id=conversation_id, tenant_id=tenant_id
                )
                db.add(conversation)
                await db.flush()
            message = Message(
                conversation_pk=conversation.id,
                role=role,
                content=content,
                tenant_id=tenant_id,
            )
            db.add(message)
            await db.commit()
            await db.refresh(message)
            return message

        except Exception:
            await db.rollback()
            raise

    async def update_resolution(
        db: AsyncSession, conversation_id: str, status: str, reason: str, tenant_id: int
    ) -> Conversation | None:
        result = await db.execute(
            select(Conversation).where(
                Conversation.conversation_id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            return None
        conversation.status = status
        conversation.resolved_by = "ai"
        conversation.resolution_reason = reason
        if status == "resolved":
            conversation.resolved_at = func.now()
        else:
            conversation.resolved_at = None
        await db.flush()
        return conversation

    async def update_conversation_status(
        db: AsyncSession, conversation_id: str, status: str, tenant_id: int
    ) -> Conversation | None:
        result = await db.execute(
            select(Conversation).where(
                Conversation.conversation_id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            return None
        conversation.status = status
        await db.flush()
        return conversation
