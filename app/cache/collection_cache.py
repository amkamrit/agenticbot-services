import json
import logging

from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client
from app.repositories.collection_repository import CollectionRepository

logger = logging.getLogger(__name__)


class CollectionCache:
    CACHE_TTL = 86400

    @classmethod
    def _get_key(cls, tenant_id: int):
        return f"tenant_id:{tenant_id}_collection"

    @classmethod
    async def get_collection(cls, tenant_id: int) -> dict:
        key = cls._get_key(tenant_id)
        try:
            cached = await redis_client.get(key)
            if cached is not None:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Redis get error for collection key %s: %s", key, exc)

        async with AsyncSessionLocal() as db:
            records = await CollectionRepository.get_collection(
                db=db, tenant_id=tenant_id
            )
            formatted = [
                {
                    "id": r.id,
                    "tenant_id": r.tenant_id,
                    "status": r.status,
                    "data": r.data,
                    "create_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
            if formatted:
                try:
                    await redis_client.set(key, json.dumps(formatted), ex=cls.CACHE_TTL)
                except Exception:
                    pass
                return formatted
        return {}

    @classmethod
    async def clear_redis(cls, tenant_id: int) -> None:
        key = cls._get_key(tenant_id)
        try:
            await redis_client.delete(key)
        except Exception as exc:
            logger.warning("Redis delete error for collection key %s: %s", key, exc)
