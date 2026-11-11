from abc import ABC, abstractmethod


class BaseEmbedding(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
