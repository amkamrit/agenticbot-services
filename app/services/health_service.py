import logging

import httpx
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


class HealthService:
    @staticmethod
    async def health_check():
        url = settings.QC_BASE_URL
        logger.info("Checking QuickConnect end point health")
        try:
            async with httpx.AsyncClient(
                timeout=10,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                return {
                    "service": "QuickConnect",
                    "url": url,
                    "status": ("healthy" if response.is_success else "unhealthy"),
                    "http_status_code": response.status_code,
                }

        except httpx.TimeoutException:
            return {
                "service": "QuickConnect",
                "url": url,
                "status": "unhealthy",
                "message": "Request timed out",
            }
        except httpx.RequestError as exc:
            return {
                "service": "QuickConnect",
                "url": url,
                "status": "unhealthy",
                "message": f"Connection failed: {type(exc).__name__}",
            }

    @staticmethod
    async def pgsql_health_check(db: AsyncSession):
        try:
            await db.execute(text("SELECT 1"))
            return {"service": "PostgreSQL", "status": "healthy"}
        except SQLAlchemyError:
            logger.error("PostgreSQL health check failed.")
            return {"service": "PostgreSQL", "status": "unhealthy"}
