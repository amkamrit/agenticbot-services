from abc import ABC, abstractmethod


class BaseVectorStore(ABC):
    @abstractmethod
    async def search(
        self, collection: str, vectors: list[float], tenant_id: int, limit: int = 5
    ):
        raise NotImplementedError
