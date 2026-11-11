import logging

import httpx

logger = logging.getLogger(__name__)


class ActionDispatcher:
    @classmethod
    def _substitute_placeholders(cls, obj: any, collected_data: dict[str, any]) -> any:
        if isinstance(obj, str):
            for key, val in collected_data.items():
                obj = obj.replace(f"{{{key}}}", str(val))
            return obj
        elif isinstance(obj, dict):
            return {
                k: cls._substitute_placeholders(v, collected_data)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [cls._substitute_placeholders(item, collected_data) for item in obj]
        return obj

    @classmethod
    async def dispatch_action(
        cls,
        tenant_id: int,
        action_config: dict[str, any],
        collected_data: dict[str, any],
    ) -> bool:
        if not action_config:
            return False
        action_type = action_config.get("type", "http_request")
        if action_type != "http_request":
            return False
        url = action_config.get("url")
        method = action_config.get("method", "POST").upper()
        headers = action_config.get("headers", {})
        payload_template = action_config.get("payload_template", {})
        prepared_body = cls._substitute_placeholders(payload_template, collected_data)
        prepared_headers = cls._substitute_placeholders(headers, collected_data)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(
                    method=method, url=url, headers=prepared_headers, json=prepared_body
                )
                logger.info(
                    "Tenant %s action executed: %s %s -> HTTP %s",
                    tenant_id,
                    method,
                    url,
                    response.status_code,
                )
                return response.is_success
        except Exception as exc:
            logger.error(
                "Failed to execute post-collection action for tenant %s: %s",
                tenant_id,
                exc,
            )
            return False
