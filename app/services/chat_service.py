import logging

from app.core.config import settings
from app.llm.schemas import LLMRequest
from app.repositories.chat_repository import ChatRepository

logger = logging.getLogger(__name__)
from app.llm.factory import create_llm_provider

llm_provider = create_llm_provider(settings)
import asyncio

from fastapi import BackgroundTasks

from app.cache.chat_cache import ChatCache
from app.core.database import AsyncSessionLocal
from app.core.json_utils import safe_parse_json
from app.orchestrator.router import WorkflowRouter, WorkflowType
from app.services.agent_service import AgentIntentService
from app.services.collection_service import CollectionService
from app.services.context_resolver_service import ContextResolverService
from app.services.mcp_service import MCPService
from app.services.prompt_service import PromptService
from app.services.resolution_service import ResolutionService
from app.services.retrieval_service import RetrievalService
from app.tasks.chat_persistence import save_message_to_db


async def _evaluate_resolution_bg(
    all_context: list, conversation_id: str, tenant_id: int
):
    try:
        resolution = await ResolutionService.evaluate(conversation_history=all_context)
        if resolution:
            async with AsyncSessionLocal() as db:
                await ChatRepository.update_resolution(
                    db=db,
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    status=resolution.status,
                    reason=resolution.reason,
                )
    except Exception:
        logger.exception(
            "Background resolution evaluation failed for conversation_id=%s, tenant_id=%s",
            conversation_id,
            tenant_id,
        )


class ChatService:
    @staticmethod
    async def chat(data, background_tasks: BackgroundTasks):
        try:
            asyncio.create_task(
                save_message_to_db(
                    conversation_id=data.id,
                    role="user",
                    content=data.message,
                    tenant_id=data.tenant_id,
                )
            )
            await ChatCache.save_conversation(
                conversation_id=data.id,
                tenant_id=data.tenant_id,
                messages=[{"role": "user", "content": data.message}],
                # is_new=True,
            )

            # Retrieve conversations history
            all_context = await ChatCache.get_conversation(
                conversation_id=data.id, tenant_id=data.tenant_id
            )
            # Determine workflow and state

            decision = await WorkflowRouter.route(
                tenant_id=data.tenant_id,
                conversation_id=data.id,
                message=data.message,
                conversation_history=all_context,
            )
            if decision.workflow == WorkflowType.HUMAN_ESCALATION:
                async with AsyncSessionLocal() as db:
                    await ChatRepository.update_conversation_status(
                        db=db,
                        conversation_id=data.id,
                        tenant_id=data.tenant_id,
                        status="assign",
                    )
                return {
                    "id": data.id,
                    "message": "Your request to speak with a human agent has been identified.",
                    "workflow": "human_escalation",
                }
            elif decision.workflow == WorkflowType.IDLE:
                cancel_reply = "Your previous request has been cancelled. How else can I assist you today?"
                asyncio.create_task(
                    save_message_to_db(
                        conversation_id=data.id,
                        role="assistant",
                        content=cancel_reply,
                        tenant_id=data.tenant_id,
                    )
                )
                await ChatCache.save_conversation(
                    conversation_id=data.id,
                    tenant_id=data.tenant_id,
                    messages=[{"role": "assistant", "content": cancel_reply}],
                )
                return {
                    "id": data.id,
                    "message": cancel_reply,
                    "workflow": "idle",
                }
            elif decision.workflow == WorkflowType.MCP:
                mcp_result = await MCPService.process_turn(
                    tenant_id=data.tenant_id,
                    conversation_id=data.id,
                    message=data.message,
                    conversation_history=all_context,
                )
                mcp_reply = mcp_result["message"]
                asyncio.create_task(
                    save_message_to_db(
                        conversation_id=data.id,
                        role="assistant",
                        content=mcp_reply,
                        tenant_id=data.tenant_id,
                    )
                )
                await ChatCache.save_conversation(
                    conversation_id=data.id,
                    tenant_id=data.tenant_id,
                    messages=[{"role": "assistant", "content": mcp_reply}],
                )
                return mcp_result
            elif decision.workflow == WorkflowType.FORM_COLLECTION:
                collection_result = await CollectionService.process_turn(
                    tenant_id=data.tenant_id,
                    conversation_id=data.id,
                    message=data.message,
                )
                asyncio.create_task(
                    save_message_to_db(
                        conversation_id=data.id,
                        role="assistant",
                        content=collection_result["message"],
                        tenant_id=data.tenant_id,
                    )
                )
                await ChatCache.save_conversation(
                    conversation_id=data.id,
                    tenant_id=data.tenant_id,
                    messages=[
                        {"role": "assistant", "content": collection_result["message"]}
                    ],
                )
                return collection_result
            else:
                latest_messages = all_context[-2:]
                latest_10_messages = all_context[-10:]

                agent_intent = await AgentIntentService.detect(
                    message=data.message, previous_message=latest_messages
                )
                # Detect human-agent request
                if agent_intent and agent_intent.wants_agent:
                    async with AsyncSessionLocal() as db:
                        await ChatRepository.update_conversation_status(
                            db=db,
                            conversation_id=data.id,
                            tenant_id=data.tenant_id,
                            status="assign",
                        )
                        return {
                            "id": data.id,
                            "message": "Your request to speak with a human agent has been identified.",
                            "agent_intent": agent_intent.model_dump(),
                        }
                # Resolve follow-up question
                context_resolution = await ContextResolverService.resolve(
                    current_question=data.message,
                    conversation_history=latest_10_messages,
                )
                search_question = context_resolution.standalone_question

                # Retrieve relevant knowledge (graceful fallback if vector DB is unreachable)
                try:
                    relevant_chunks = await RetrievalService.relevant_chunks(
                        question=search_question, tenant_id=data.tenant_id, limit=5
                    )
                except Exception as exc:
                    logger.warning(
                        "Vector retrieval failed, continuing with direct LLM: %s", exc
                    )
                    relevant_chunks = []
                # Generate LLM prompt
                llm_messages = PromptService.generate_chat_prompt(
                    question=search_question, context=relevant_chunks
                )
                llm_request = LLMRequest(message=llm_messages)

                # Generate LLM response

                llm_response = await llm_provider.generate(llm_request)

                response_data = safe_parse_json(llm_response.message)

                if (
                    not response_data
                    or response_data.get("has_sufficient_information") is False
                ):
                    clean_answer = (
                        "I don't have enough information to answer "
                        "your question. Would you like to speak "
                        "with a human agent?"
                    )
                else:
                    clean_answer = response_data.get("answer", llm_response.message)

                asyncio.create_task(
                    save_message_to_db(
                        conversation_id=data.id,
                        role="assistant",
                        content=clean_answer,
                        tenant_id=data.tenant_id,
                    )
                )
                await ChatCache.save_conversation(
                    conversation_id=data.id,
                    tenant_id=data.tenant_id,
                    messages=[{"role": "assistant", "content": clean_answer}],
                )
                background_tasks.add_task(
                    _evaluate_resolution_bg,
                    all_context=all_context,
                    conversation_id=data.id,
                    tenant_id=data.tenant_id,
                )
            # Return response
            return {
                "id": data.id,
                "message": clean_answer,
                "all_context": all_context,
                "model": llm_response.model,
                "usage": {
                    "prompt_tokens": llm_response.prompt_tokens,
                    "completion_tokens": llm_response.completion_tokens,
                    "total_tokens": llm_response.total_tokens,
                },
            }
        except Exception:
            logger.exception("Failed to process chat request")
            raise
