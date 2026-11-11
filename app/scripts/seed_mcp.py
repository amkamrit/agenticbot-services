import asyncio
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.mcp_collection import MCPCollection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TENANT_ID = 100

TENANT_100_MCP_CONFIG = {
    "url": "http://localhost:9091",
    "auth": {
        "enabled": False,
        "type": None,
        "credentials": None,
    },
}


async def seed_tenant_100_mcp():
    logger.info("Seeding MCP configuration for tenant_id=%s...", TENANT_ID)

    async with AsyncSessionLocal() as db:
        stmt = select(MCPCollection).where(
            MCPCollection.tenant_id == TENANT_ID,
            MCPCollection.status == "active",
        )

        result = await db.execute(stmt)
        record = result.scalars().first()

        if record:
            record.data = TENANT_100_MCP_CONFIG
            logger.info("Updated existing MCP config for tenant %s", TENANT_ID)
        else:
            record = MCPCollection(
                tenant_id=TENANT_ID,
                status="active",
                data=TENANT_100_MCP_CONFIG,
            )
            db.add(record)
            logger.info("Created new MCP config for tenant %s", TENANT_ID)

        await db.commit()

    logger.info("MCPCollection configuration seeded successfully.")


if __name__ == "__main__":
    asyncio.run(seed_tenant_100_mcp())
