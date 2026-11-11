from app.core.config import settings
from app.embeddings.factory import create_embedding_provider
from app.vector_store.factory import create_vector_store_provider


class RetrievalService:
    @staticmethod
    async def relevant_chunks(
        question: str, tenant_id: int, limit: int = 5
    ) -> list[str]:
        embedding = create_embedding_provider(settings)
        vector_store = create_vector_store_provider(settings)
        question_vector = await embedding.embed(question)
        collection_name = f"tenant_{tenant_id}_knowledge"

        results = await vector_store.search(
            collection=collection_name,
            vector=question_vector,
            limit=limit,
            tenant_id=tenant_id,
        )
        chunks = []
        for result in results:
            for hit in result:
                entity = hit.get("entity", {})
                text = entity.get("text")

                if text:
                    chunks.append(text)
        return chunks
