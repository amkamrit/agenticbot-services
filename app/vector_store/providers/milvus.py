import asyncio
import logging

from pymilvus import MilvusClient

from app.core.config import Settings
from app.vector_store.base import BaseVectorStore

logger = logging.getLogger(__name__)


class Milvus(BaseVectorStore):
    def __init__(self, settings: Settings):
        self.client = MilvusClient(uri=settings.MILVUS_URL)

    def _search_sync(
        self, collection: str, vector: list[float], limit: int, filter_expr: str
    ):
        """Checks existence, loads into memory, and performs search synchronously."""
        # 1. Check if collection exists
        if not self.client.has_collection(collection_name=collection):
            logger.warning("Milvus collection '%s' does not exist.", collection)
            return []

        # 2. Check load state; if not loaded into memory, load it now!
        load_state = self.client.get_load_state(collection_name=collection)
        state = (
            load_state.get("state") if isinstance(load_state, dict) else str(load_state)
        )
        if str(state).lower() != "loaded":
            logger.info("Loading Milvus collection '%s' into memory...", collection)
            self.client.load_collection(collection_name=collection)

        # 3. Execute search
        return self.client.search(
            collection_name=collection,
            data=[vector],
            limit=limit,
            filter=filter_expr,
            output_fields=["text", "url", "title", "chunk_index"],
        )

    async def search(
        self, collection: str, vector: list[float], tenant_id: int, limit: int = 5
    ):
        try:
            filter_expr = (
                f"tenant_id =={tenant_id}" if tenant_id and tenant_id > 0 else ""
            )
            results = await asyncio.to_thread(
                self._search_sync,
                collection,
                vector,
                limit,
                filter_expr,
            )
            return results

        except Exception:
            logger.exception("Milvus search failed")
            raise
