from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.health_service import HealthService

health_router = APIRouter(prefix="/health", tags=["Health"])


@health_router.get("/")
async def health(db: AsyncSession = Depends(get_db)):
    quick_connect = await HealthService.health_check()
    postgres = await HealthService.pgsql_health_check(db)
    response = {"quick_connect": quick_connect, "postgres": postgres}
    return response
