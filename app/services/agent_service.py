import logging

from app.core.config import settings
from app.llm.factory import create_llm_provider
from app.llm.schemas import LLMMessage, LLMRequest
from app.schemas.agent_intent import AgentIntentResult

logger = logging.getLogger(__name__)


llm_provider = create_llm_provider(settings)


class AgentIntentService:
    async def detect(
        message: str, previous_message: str | None = None
    ) -> AgentIntentResult | None:
        try:
            prompt = f"""
            You are a customer support intent detection system.

Determine whether the customer wants to speak with a human support agent.

Return ONLY valid JSON:
{{
    "wants_agent": true,
    "intent": "request_agent",
    "reason": "Customer requested human support.",
    "confidence": 0.98
}}

Rules:
- request_agent: Customer explicitly requests human support
  OR accepts an earlier offer to speak with an agent.
- continue_ai: Customer wants to continue with AI assistance.
- uncertain: Customer intention is unclear.
- Understand natural language confirmations such as:
  yes, yep, sure, okay, absolutely, go ahead, please do.
- Understand natural language refusals such as:
  no, nope, not now, no thanks.
- Frustration alone does not mean the customer wants an agent.
- Consider the previous assistant message when interpreting
  short responses like yes, okay, and sure.

Previous assistant message:
{previous_message or "None"}

Customer message:
{message}
"""
            response = await llm_provider.generate(
                LLMRequest(
                    message=[
                        LLMMessage(
                            role="user",
                            message=prompt,
                        )
                    ]
                )
            )
            return AgentIntentResult.model_validate_json(response.message)
        except Exception:
            logger.exception("Agent intent detection failed")
            return None
