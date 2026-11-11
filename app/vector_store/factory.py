from app.core.config import Settings
from app.vector_store.base import BaseVectorStore
from app.vector_store.providers.milvus import Milvus


def create_vector_store_provider(settings: Settings) -> BaseVectorStore:
    provider = settings.VECTORSTORE_PROVIDER.lower()
    if provider == "milvus":
        return Milvus(settings)
    raise ValueError(f"Unsupported vector store provider: {provider}")
