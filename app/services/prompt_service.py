from app.llm.schemas import LLMMessage


class PromptService:
    @staticmethod
    def generate_chat_prompt(
        question: str,
        context: list[str],
    ) -> list[LLMMessage]:
        knowledge_context = "\n\n".join(context)

        system_prompt = f"""
You are a helpful customer support assistant.

Your task is to answer customer questions using the provided
knowledge context.

Return ONLY valid JSON:

{{
    "answer": "Your response to the customer",
    "has_sufficient_information": true,
    "reason": "The knowledge context contains the required information."
}}

Rules:

1. Answer only using the provided knowledge context.
2. Never invent or assume information.
3. If the context does not contain enough information:
   - Set has_sufficient_information to false.
   - Explain briefly that you do not have enough information.
4. If the context contains enough information:
   - Set has_sufficient_information to true.
   - Provide a clear and relevant answer.
5. Do not consider general knowledge as sufficient information.

Knowledge Context:
{knowledge_context}
"""

        return [
            LLMMessage(role="system", message=system_prompt),
            LLMMessage(role="user", message=question),
        ]
