from fastapi import APIRouter

from app.api.v1.endpoints.chat import chat_router
from app.api.v1.endpoints.health import health_router

v1_router = APIRouter(
    prefix="/api/v1",
)
v1_router.include_router(health_router)
v1_router.include_router(chat_router)
