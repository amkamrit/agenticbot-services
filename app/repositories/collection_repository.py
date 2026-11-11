import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.form_collection import FormCollection

logger = logging.getLogger(__name__)


class FormRepository:
    @staticmethod
    async def get_latest_collection(
        db: AsyncSession, tenant_id: int
    ) -> FormCollection | None:
        result = await db.execute(
            select(FormCollection)
            .where(FormCollection.tenant_id == tenant_id)
            .order_by(FormCollection.created_at.desc())
        )
        return list(result.scalars().all())
