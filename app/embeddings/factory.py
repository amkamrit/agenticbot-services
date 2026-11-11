from app.core.config import Settings
from app.embeddings.base import BaseEmbedding
from app.embeddings.providers.ollama import OllamaEmbedding


def create_embedding_provider(settings: Settings) -> BaseEmbedding:
    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "ollama":
        return OllamaEmbedding(settings)
    raise ValueError(f"Unsupported embedding provider: {provider}")
