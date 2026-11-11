from app.core.config import settings
from app.core.json_utils import safe_parse_json
from app.llm.factory import create_llm_provider
from app.llm.schemas import LLMMessage, LLMRequest
from app.orchestrator.session_models import RoutingDecision, WorkflowType
from app.orchestrator.state_manager import SessionStateManager

_llm_provider = create_llm_provider(settings)

CANCEL_PHRASES = {
    "cancel",
    "stop",
    "abort",
    "quit",
    "nevermind",
    "restart",
    "reset",
    "exit",
}
HUMAN_KEYWORDS = {
    "human",
    "agent",
    "operator",
    "representative",
    "support desk",
    "person",
    "live support",
}


QUESTION_STARTERS = (
    "what",
    "how",
    "where",
    "why",
    "when",
    "who",
    "which",
    "can you",
    "could you",
    "do you",
    "does",
    "is there",
    "is it",
    "tell me",
    "explain",
)

SWITCH_INTENT_KEYWORDS = (
    "check billing",
    "billing status",
    "my bill",
    "unpaid bill",
    "invoice",
    "check balance",
)


class WorkflowRouter:
    @classmethod
    async def route(
        cls,
        tenant_id: str,
        conversation_id: str,
        message: str,
        conversation_history: list[dict[str, any]] | None = None,
    ) -> RoutingDecision:
        clean_msg = message.strip()
        lower_msg = clean_msg.lower()

        state = await SessionStateManager.get_state(tenant_id, conversation_id)

        # 1. Cancellations
        if state.is_in_active_flow() and any(
            lower_msg == phrase or lower_msg.startswith(f"{phrase}")
            for phrase in CANCEL_PHRASES
        ):
            state = await SessionStateManager.reset_to_idle(tenant_id, conversation_id)
            return RoutingDecision(
                workflow=WorkflowType.IDLE,
                state=state,
                is_continuation=False,
                reason="User cancelled active workflow",
            )

        # 2. Human escalation request takes priority even during active flows
        if any(kw in lower_msg for kw in HUMAN_KEYWORDS) and (
            "talk" in lower_msg
            or "speak" in lower_msg
            or "connect" in lower_msg
            or "transfer" in lower_msg
            or "need" in lower_msg
            or "want" in lower_msg
            or "person" in lower_msg
            or "agent" in lower_msg
            or "operator" in lower_msg
        ):
            new_state = await SessionStateManager.set_workflow(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                workflow=WorkflowType.HUMAN_ESCALATION,
            )
            return RoutingDecision(
                workflow=WorkflowType.HUMAN_ESCALATION,
                state=new_state,
                is_continuation=False,
                confidence=0.98,
                reason="Explicit customer request for human agent",
            )

        # 3. Active Human Escalation session continuation
        if state.active_workflow == WorkflowType.HUMAN_ESCALATION:
            return RoutingDecision(
                workflow=WorkflowType.HUMAN_ESCALATION,
                state=state,
                is_continuation=True,
                reason="Session already escalated to human agent",
            )

        # 4. Active MCP tool continuation
        if state.active_workflow == WorkflowType.MCP:
            # Only continue MCP if there is an active pending tool action in metadata
            if state.workflow_metadata and state.workflow_metadata.get("pending_tool_action"):
                return RoutingDecision(
                    workflow=WorkflowType.MCP,
                    state=state,
                    is_continuation=True,
                    reason="Continuing active MCP tool workflow",
                )
            # If no pending action, reset state to idle to prevent deadlock trap
            state = await SessionStateManager.reset_to_idle(tenant_id, conversation_id)

        # 5. Active Form Collection continuation (with digression & intent switch support)
        if state.active_workflow == WorkflowType.FORM_COLLECTION:
            is_question = clean_msg.endswith("?") or any(
                lower_msg.startswith(f"{starter} ") or lower_msg == starter
                for starter in QUESTION_STARTERS
            )
            is_intent_switch = any(
                kw in lower_msg for kw in SWITCH_INTENT_KEYWORDS
            )
            # If user is answering slot questions (e.g. "SMS", "9841...", "Encraft Tech"), continue form
            if not is_question and not is_intent_switch:
                return RoutingDecision(
                    workflow=WorkflowType.FORM_COLLECTION,
                    state=state,
                    is_continuation=True,
                    reason="Continuing active form collection workflow with user slot response",
                )
            # If it's a question ("what is quickconnect?") or intent switch ("check billing"), let classifier handle it!
        classified_type, confidence, reason = await cls._classify_intent_llm(
            message=clean_msg, history=conversation_history
        )
        if classified_type in (WorkflowType.MCP, WorkflowType.FORM_COLLECTION):
            state = await SessionStateManager.set_workflow(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                workflow=classified_type,
            )
        elif classified_type == WorkflowType.HUMAN_ESCALATION:
            state = await SessionStateManager.set_workflow(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                workflow=WorkflowType.HUMAN_ESCALATION,
            )
        else:
            if state.active_workflow != WorkflowType.FORM_COLLECTION:
                state.active_workflow = WorkflowType.RAG
                await SessionStateManager.save_state(state)
        return RoutingDecision(
            workflow=classified_type,
            state=state,
            is_continuation=False,
            confidence=confidence,
            reason=reason,
        )

    @classmethod
    async def _classify_intent_llm(
        cls, message: str, history: list[dict[str, any]] | None
    ) -> tuple[WorkflowType, float, str]:
        recent_history = ""
        if history:
            formatted = [
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history[-3:]
            ]
            recent_history = "\n".join(formatted)

        prompt = f"""You are a SaaS conversational intent classifier.
Analyze the customer's message and determine the correct execution workflow:

Categories:
1. "mcp": The user wants to perform an operational action, query real-time data, run diagnostics, or execute account operations.
Examples:
- "My internet is slow, run diagnostics on account 984123"
- "Verify my OTP 8492"
- "Check my current account balance or plan status"
- "Reboot my router or reset my Wi-Fi"
- "Check my unpaid billing status"

2. "form_collection": The user wants to register, onboard, sign up, submit details, or apply for an account/service.
Examples:
- "I want to register my company"
- "Sign me up for enterprise service"
- "How can I register? Here are my company details"
- "Start my KYC onboarding"

3. "human_escalation": The user explicitly requests to speak with a human support agent or operator.
Examples:
- "I want to talk to a human agent"
- "Transfer me to an operator"

4. "rag": The user is asking general informational questions, FAQs, pricing overviews, company background, or policy inquiries.
Examples:
- "What is QuickConnect?"
- "What are your business hours?"
- "Which messaging channels do you support?"
- "Tell me about your pricing"

Recent Conversation Context:
{recent_history or "None"}

Customer Message:
"{message}"

Return ONLY valid JSON:
{{
    "workflow": "mcp" | "form_collection" | "rag" | "human_escalation",
    "confidence": 0.95,
    "reason": "Brief explanation of why this workflow was selected"
}}
"""
        try:
            llm_req = LLMRequest(
                message=[LLMMessage(role="user", message=prompt)],
                temperature=0.1,
                max_output_tokens=150,
            )
            response = await _llm_provider.generate(llm_req)
            if response and response.message:
                parsed = safe_parse_json(response.message)
                if parsed and "workflow" in parsed:
                    target_str = str(parsed["workflow"]).lower().strip()
                    conf = float(parsed.get("confidence", 0.9))
                    reason = str(parsed.get("reason", ""))

                    if target_str == "mcp":
                        return WorkflowType.MCP, conf, reason
                    if target_str in ("form_collection", "from", "onboarding"):
                        return WorkflowType.FORM_COLLECTION, conf, reason
                    if target_str in ("human_escalation", "human", "agent"):
                        return WorkflowType.HUMAN_ESCALATION, conf, reason
                    return WorkflowType.RAG, conf, reason
        except Exception:
            return WorkflowType.RAG, 0.7, "Default fallback to knowledge base"
