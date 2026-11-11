import logging

from groq import (
    AsyncGroq,
)

from app.core.config import Settings
from app.llm.base import BaseLLMProvider
from app.llm.schemas import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class GroqProvider(BaseLLMProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

        self.client = AsyncGroq(
            api_key=settings.GROQ_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )
        self.model = settings.GROQ_MODEL

    async def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": item.role,
                        "content": item.message,
                    }
                    for item in request.message
                ],
                max_tokens=self.settings.LLM_MAX_OUTPUT_TOKENS,
                temperature=self.settings.LLM_TEMPERATURE,
            )
            content = response.choices[0]
            return LLMResponse(
                message=content.message.content or "", provider="groq", model=self.model
            )
        except Exception as exc:
            logger.exception("Unexpected Groq error: %s", str(exc))

    async def close(self) -> None:
        await self.client.close()
