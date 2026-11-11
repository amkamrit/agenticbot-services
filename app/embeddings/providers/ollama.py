import logging

import httpx

from app.core.config import Settings
from app.embeddings.base import BaseEmbedding

logger = logging.getLogger(__name__)

_shared_client: httpx.AsyncClient | None = None


def get_shared_ollama_client(base_url: str, timeout: int) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=200),
        )
    return _shared_client


class OllamaEmbedding(BaseEmbedding):
    def __init__(self, settings: Settings):
        self.base_url = settings.OLLAMA.rstrip("/")
        self.model = settings.OLLAMA_MODEL

        self.client = get_shared_ollama_client(
            base_url=self.base_url, timeout=settings.LLM_TIMEOUT_SECONDS
        )

    async def embed(self, text: str) -> list[float]:
        try:
            response = await self.client.post(
                "/api/embed", json={"model": self.model, "input": text}
            )
            response.raise_for_status()
            data = response.json()
            return data["embeddings"][0]
        except Exception as exc:
            logger.exception("Ollama embedding error : %s", str(exc))

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self.client.post(
                "/api/embed", json={"model": self.model, "input": texts}
            )
            response.raise_for_status()
            data = response.json()
            return data["embeddings"]
        except Exception as exc:
            logger.exception("Ollama embedding error : %s", str(exc))
