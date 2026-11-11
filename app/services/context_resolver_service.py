from app.core.config import settings
from app.core.json_utils import safe_parse_json
from app.llm.factory import create_llm_provider
from app.llm.schemas import ContextResolution, LLMMessage, LLMRequest

llm_provider = create_llm_provider(settings)


class ContextResolverService:
    @staticmethod
    async def resolve(
        current_question: str,
        conversation_history: list,
    ) -> ContextResolution:
        prompt = f"""
 You are a conversational context resolver.

        Analyze the current question using conversation history.

        Determine whether the current question is a follow-up.

        Rules:
        1. Resolve short questions using previous conversation.
        2. Preserve the previous topic when the user refers to it.
        3. Do not force unrelated questions into previous topics.
        4. Convert follow-up questions into standalone questions.
        5. If the question is already standalone, preserve its meaning.

        Conversation:
        {conversation_history}

        Current question:
        {current_question}

        Return JSON:
        {{
            "is_follow_up": true,
            "standalone_question": "...",
            "topic": "..."
        }}        
"""
        llm_request = LLMRequest(
            message=[
                LLMMessage(role="system", message=prompt),
                LLMMessage(role="user", message=prompt),
            ]
        )
        response = await llm_provider.generate(llm_request)
        parsed = safe_parse_json(response.message)
        if parsed and "standalone_question" in parsed:
            try:
                return ContextResolution.model_validate(parsed)
            except Exception:
                pass
        return ContextResolution(
            is_follow_up=False, standalone_question=current_question, topic="general"
        )

        return ContextResolution.model_validate_json(response.message)
