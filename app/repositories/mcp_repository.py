import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_collection import MCPCollection

logger = logging.getLogger(__name__)


class MCPRepository:
    @staticmethod
    async def get_mcp(db: AsyncSession, tenant_id: int) -> MCPCollection | None:
        result = await db.execute(
            select(MCPCollection)
            .where(MCPCollection.tenant_id == tenant_id)
            .order_by(MCPCollection.created_at.desc())
        )
        return list(result.scalars().all())
