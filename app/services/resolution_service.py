import logging

from app.core.config import settings
from app.core.json_utils import safe_parse_json
from app.llm.factory import create_llm_provider
from app.llm.schemas import LLMMessage, LLMRequest
from app.schemas.resolution import ResolutionResult

logger = logging.getLogger(__name__)

llm_provider = create_llm_provider(settings)


class ResolutionService:
    @staticmethod
    async def evaluate(conversation_history: list) -> ResolutionResult | None:
        try:
            conversation_text = "\n".join(
                f"{m.get('role') if isinstance(m, dict) else m.role}:{m.get('content') if isinstance(m, dict) else m.content}"
                for m in conversation_history
            )
            system_prompt = """
            You are an AI customer support conversation resolution evaluator.

Your task is to determine the current state of a customer support conversation.

Evaluation rules:

1. resolved:
   - The customer's issue has clearly been solved.
   - The customer explicitly confirms the solution worked.
   - The conversation provides strong evidence that the requested issue is completed.

2. active:
   - The customer still has questions or unresolved issues.
   - The assistant needs to provide additional assistance.
   - The customer reports that the solution did not work.

3. pending:
   - The assistant has provided a solution but needs customer confirmation.
   - The conversation is waiting for additional information or a response.

4. escalated:
   - The customer requests human support.
   - The issue requires human intervention.
   - The assistant cannot appropriately handle the request.

Important:
- Do not mark a conversation resolved simply because the assistant answered.
- Do not consider silence or lack of a follow-up message as proof of resolution.
- Evaluate the entire conversation, not just the last message.
- Never invent customer confirmation.

Return ONLY valid JSON in this format:

{
    "status": "active",
    "reason": "The customer's issue is still unresolved.",
    "confidence": 0.95
}
"""
            llm_request = LLMRequest(
                message=[
                    LLMMessage(role="system", message=system_prompt),
                    LLMMessage(
                        role="user",
                        message=f"Evaluate this conversation:\n\n{conversation_text}",
                    ),
                ]
            )
            response = await llm_provider.generate(llm_request)
            parsed = safe_parse_json(response.message)
            if parsed:
                return ResolutionResult.model_validate(parsed)
            return None
        except Exception:
            logger.exception("Conversation resolution evaluation failed")
            return None
