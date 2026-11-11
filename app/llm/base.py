from abc import ABC, abstractmethod

from app.llm.schemas import LLMRequest, LLMResponse


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
