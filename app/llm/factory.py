import logging

from app.core.config import Settings
from app.llm.base import BaseLLMProvider
from app.llm.providers.groq import GroqProvider
from app.llm.providers.huggingface import HuggingFaceProvider

logger = logging.getLogger(__name__)


def create_llm_provider(
    settings: Settings,
) -> BaseLLMProvider:

    provider_name = settings.LLM_PROVIDER.lower()
    if provider_name == "groq":
        return GroqProvider(settings)
    if provider_name == "huggingface":
        return HuggingFaceProvider(settings)
    else:
        logger.error(f"Unsupported LLM provider: {provider_name}")
