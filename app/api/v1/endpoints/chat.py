from fastapi import APIRouter, BackgroundTasks

chat_router = APIRouter(prefix="/chat", tags=["Chat"])
from app.schemas.chat_request import ChatRequest
from app.services.chat_service import ChatService


@chat_router.post("/")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    return await ChatService.chat(request, background_tasks)
