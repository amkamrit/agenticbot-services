import logging

from app.core.database import AsyncSessionLocal
from app.llm.schemas import LLMMessage, LLMRequest
from app.repositories.mcp_repository import MCPRepository

logger = logging.getLogger(__name__)
import json

from mcp import ClientSession
from mcp.client.sse import sse_client

from app.core.config import settings
from app.core.json_utils import safe_parse_json
from app.llm.factory import create_llm_provider
from app.orchestrator.state_manager import SessionStateManager

_llm_provider = create_llm_provider(settings)


class MCPService:
    @classmethod
    async def get_all_mcp_server_url(
        cls, tenant_id: int
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        servers = []
        async with AsyncSessionLocal() as db:
            mcp_collection = await MCPRepository.get_mcp(db=db, tenant_id=tenant_id)
            if not mcp_collection:
                return []
            for record in mcp_collection:
                data = record.data or {}
                server_url = data.get("url")
                if not server_url:
                    continue
                headers = {}
                auth = data.get("auth") or {}
                server_creds = auth.get("credentials") or {}
                tool_credentials = (
                    auth.get("tool_credentials") or data.get("tool_credentials") or {}
                )
                if auth.get("enabled"):
                    if server_creds.get("api_key"):
                        headers["X-API-Key"] = server_creds["api_key"]
                bearer_token = tool_credentials.get("bearer_token")
                api_token = tool_credentials.get("api_token")

                if bearer_token:
                    clean_bearer = bearer_token.replace("Bearer", "").strip()
                    headers["Authorization"] = f"Bearer {clean_bearer}"
                if api_token:
                    headers["Api-Token"] = api_token.strip()

                servers.append(
                    {
                        "url": server_url,
                        "headers": headers,
                        "tool_credentials": tool_credentials,
                    }
                )
        logger.info(
            ">>> [DEBUG 1] Loaded servers for tenant %s: %s", tenant_id, servers
        )
        return servers

    @classmethod
    async def execute_tool_call(
        cls,
        server_url: str,
        tool_name: str,
        arguments: dict[str, any],
        headers: dict[str, any] | None = None,
    ) -> any:
        logger.info(
            ">>> [DEBUG 2] Tool: %s | Headers Sent: %s | Args Sent: %s",
            tool_name,
            headers,
            arguments,
        )

        async with (
            sse_client(server_url, headers=headers or {}) as (
                read_stream,
                write_stream,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            logger.info(">>> [DEBUG 3] Tool Raw Response: %s", result)
            return result

    @classmethod
    async def list_available_tools(
        cls, server_url: str, headers: dict[str, str]
    ) -> list[dict[str, any]]:
        try:
            async with (
                sse_client(server_url, headers=headers or {}) as (
                    read_stream,
                    write_stream,
                ),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                response = await session.list_tools()
                tools = []
                for t in response.tools:
                    tools.append(
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.inputSchema,
                        }
                    )
                return tools
        except Exception as exc:
            logger.error(
                "Failed to fetch tools from MCP server at %s: %s", server_url, exc
            )
            return []

    @classmethod
    async def process_turn(
        cls,
        tenant_id: int,
        conversation_id: str,
        message: str,
        conversation_history: list[dict[str, any]] | None = None,
    ) -> dict[str, any]:
        servers = await cls.get_all_mcp_server_url(tenant_id)
        if not servers:
            return {
                "id": conversation_id,
                "message": "No operational tools are configured for your account.",
                "workflow": "mcp",
            }

        all_tools = []
        tool_routing_registry: dict[str, dict[str, any]] = {}
        for server in servers:
            server_tools = await cls.list_available_tools(
                server_url=server["url"], headers=server["headers"]
            )
            for tool in server_tools:
                tool_name = tool["name"]
                all_tools.append(tool)
                tool_routing_registry[tool_name] = {
                    "url": server["url"],
                    "headers": server["headers"],
                    "tool_credentials": server.get("tool_credentials", {}),
                    "input_schema": tool.get("inputSchema", {}),
                }
        if not all_tools:
            await SessionStateManager.reset_to_idle(tenant_id, conversation_id)
            return {
                "id": conversation_id,
                "message": "I'm currently unable to access the operational tools. Please try again shortly or speak with a human representative.",
                "workflow": "mcp",
            }

        CRED_KEYS = {
            "bearer_token",
            "api_token",
            "token",
            "authorization",
            "credentials",
            "headers",
            "api-token",
        }
        llm_tools = []
        for tool in all_tools:
            tool_clean = json.loads(json.dumps(tool))
            props = tool_clean.get("inputSchema", {}).get("properties", {})
            required = tool_clean.get("inputSchema", {}).get("required", {})

            for k in list(props.keys()):
                if k.lower() in CRED_KEYS:
                    del props[k]
                if isinstance(required, list):
                    tool_clean["inputSchema"]["required"] = [
                        r for r in required if r.lower() not in CRED_KEYS
                    ]
                llm_tools.append(tool_clean)

        tools_description = json.dumps(llm_tools, indent=2)
        history_context = ""
        if conversation_history:
            history_context = "\n".join(
                [
                    f"{m.get('role', 'user')}: {m.get('content', '')}"
                    for m in conversation_history[-5:]
                ]
            )
        session_state = await SessionStateManager.get_state(tenant_id, conversation_id)
        session_meta = getattr(session_state, "workflow_metadata", {}) or {}
        accumulated_args = session_meta.get("partial_arguments", {}) or {}
        prompt = f"""You are an AI assistant orchestrating operational actions using available MCP tools.

Available MCP Tools:
{tools_description}

Conversation History:
{history_context or "None"}

Session Context (values collected from previous tools/turns):
{json.dumps(accumulated_args, indent=2) if accumulated_args else "None"}

Customer Request:
"{message}"

Task:
1. Determine which tool best handles this request.
2. Extract the arguments required for the tool schema.
3. If necessary information is missing, set "missing_arguments" and ask the user for them in "follow_up_message".

Return ONLY valid JSON matching this structure:
{{
    "tool_to_call": "<tool_name or null>",
    "arguments": {{}},
    "missing_arguments": ["<arg_name>"],
    "follow_up_message": "<clarifying message to customer if arguments are missing or null>"
}}
"""
        llm_req = LLMRequest(
            message=[LLMMessage(role="user", message=prompt)],
            temperature=0.1,
            max_output_tokens=500,
        )
        llm_resp = await _llm_provider.generate(llm_req)
        decision = safe_parse_json(llm_resp.message) or {}
        tool_to_call = decision.get("tool_to_call")
        new_args = decision.get("arguments", {})
        arguments = {**accumulated_args, **new_args}
        missing_args = [
            arg
            for arg in decision.get("missing_arguments", [])
            if arg not in arguments and arg.lower() not in CRED_KEYS
        ]
        logger.info(
            ">>> LLM DECISION: tool=%s | args=%s | missing=%s",
            tool_to_call,
            arguments,
            missing_args,
        )

        if missing_args or not tool_to_call:
            clarification = decision.get(
                "follow_up_message",
                "Could you please provide the additional details required to proceed?",
            )
            await SessionStateManager.update_metadata(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                updates={
                    "pending_tool_action": tool_to_call,
                    "partial_arguments": arguments,
                },
            )
            return {"id": conversation_id, "message": clarification, "workflow": "mcp"}

        target_server = tool_routing_registry.get(tool_to_call)
        if not target_server:
            await SessionStateManager.reset_to_idle(tenant_id, conversation_id)
            return {
                "id": conversation_id,
                "message": f"Unable to locate the server responsible for {tool_to_call}.",
                "workflow": "mcp",
            }
        tool_creds = target_server.get("tool_credentials", {})
        schema_props = target_server.get("input_schema", {}).get("properties", {})
        bearer = tool_creds.get("bearer_token")
        api_token = tool_creds.get("api_token")
        logger.info(">>> TOOL SCHEMA FOR %s: %s", tool_to_call, schema_props)

        if bearer:
            arguments["bearer_token"] = bearer.replace("Bearer", "").strip()
            arguments["Authorization"] = (
                f"Bearer {bearer.replace('Bearer', '').strip()}"
            )
        if api_token:
            arguments["api_token"] = api_token.strip()
            arguments["Api-Token"] = api_token.strip()
        arguments["headers"] = target_server.get("headers", {})
        try:
            tool_result = await cls.execute_tool_call(
                server_url=target_server["url"],
                tool_name=tool_to_call,
                arguments=arguments,
                headers=target_server["headers"],
            )
            raw_text = "\n".join(
                [item.text for item in tool_result.content if hasattr(item, "text")]
            ) or str(tool_result)

            summary_prompt = f"""A customer requested: "{message}"
The tool '{tool_to_call}' was executed with result:
{raw_text}

Task:
1. Provide a concise, polite response explaining the result or asking the customer any follow-up question required by the tool.
2. Determine if the customer's goal is fully completed, or if we are waiting for the customer to reply (e.g. choose an option, provide a code/PIN, confirm an action).
Return ONLY valid JSON:
{{
    "reply": "<message to customer>",
    "is_complete": true or false
}}
"""

            summary_resp = await _llm_provider.generate(
                LLMRequest(
                    message=[LLMMessage(role="user", message=summary_prompt)],
                    temperature=0.2,
                    max_output_tokens=300,
                )
            )
            parsed_summary = safe_parse_json(summary_resp.message) or {}
            reply =parsed_summary.get("reply") or summary_resp.message.strip()
            is_complete = parsed_summary.get("is_complete", True)
            parsed_res = safe_parse_json(raw_text) or {}
            updated_context = dict(arguments)
            if isinstance(parsed_res, dict):
                for k, v in parsed_res.items():
                    if isinstance(v, (str, int, float, bool)):
                        updated_context[k] = v
            if not is_complete:
                await SessionStateManager.update_metadata(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    updates={"partial_arguments": updated_context},
                )
            else:
                await SessionStateManager.reset_to_idle(tenant_id, conversation_id)

        except Exception as exc:
            logger.error("Error executing MCP tool %s: %s", tool_to_call, exc)
            reply = f"The operation could not be completed at this time due to an error: {exc!s}"

            await SessionStateManager.reset_to_idle(tenant_id, conversation_id)

        return {
            "id": conversation_id,
            "message": reply,
            "workflow": "mcp",
            "tool_executed": tool_to_call,
        }
