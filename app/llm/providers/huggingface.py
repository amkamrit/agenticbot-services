import logging

from huggingface_hub import AsyncInferenceClient

from app.core.config import Settings
from app.llm.base import BaseLLMProvider
from app.llm.schemas import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class HuggingFaceProvider(BaseLLMProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

        self.client = AsyncInferenceClient(
            token=settings.HF_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            model=settings.HF_MODEL,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            response = await self.client.chat_completion(
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
            choice = response.choices[0]
            return LLMResponse(
                message=choice.message.content or "",
                provider="groq",
                model=self.model,
                prompt_tokens=response.usage.prompt_tokens if response.usage else None,
                completion_tokens=response.usage.completion_tokens
                if response.usage
                else None,
                total_tokens=response.usage.total_tokens if response.usage else None,
                finish_reason=choice.finish_reason,
            )
        except Exception as exc:
            logger.exception("Unexpected groq error: %s", str(exc))

    async def close(self) -> None:
        await self.client.close()
