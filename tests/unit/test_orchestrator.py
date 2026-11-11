import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.orchestrator.session_models import (
    RoutingDecision,
    SessionState,
    WorkflowType,
)
from app.orchestrator.state_manager import SessionStateManager
from app.orchestrator.router import WorkflowRouter


class TestOrchestratorState(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tenant_id = 999
        self.conversation_id = "test-conv-state-001"

    def test_session_state_defaults(self):
        state = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
        )
        self.assertEqual(state.active_workflow, WorkflowType.IDLE)
        self.assertFalse(state.is_in_active_flow())
        self.assertEqual(state.turn_count, 0)
        self.assertEqual(state.workflow_metadata, {})

        state.active_workflow = WorkflowType.MCP
        self.assertTrue(state.is_in_active_flow())

        state.active_workflow = WorkflowType.FORM_COLLECTION
        self.assertTrue(state.is_in_active_flow())

        state.touch()
        self.assertEqual(state.turn_count, 1)

    @patch("app.orchestrator.state_manager.redis_client")
    async def test_state_manager_get_and_save(self, mock_redis):
        # 1. When redis has no state
        mock_redis.get = AsyncMock(return_value=None)
        state = await SessionStateManager.get_state(self.tenant_id, self.conversation_id)
        self.assertEqual(state.active_workflow, WorkflowType.IDLE)

        # 2. Save state
        mock_redis.set = AsyncMock(return_value=True)
        saved = await SessionStateManager.save_state(state)
        self.assertTrue(saved)
        mock_redis.set.assert_called_once()

        # 3. When redis returns serialized JSON
        serialized = state.model_dump_json()
        mock_redis.get = AsyncMock(return_value=serialized)
        retrieved = await SessionStateManager.get_state(self.tenant_id, self.conversation_id)
        self.assertEqual(retrieved.tenant_id, self.tenant_id)
        self.assertEqual(retrieved.conversation_id, self.conversation_id)

    @patch("app.orchestrator.state_manager.redis_client")
    async def test_set_workflow_and_reset(self, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)

        # Set to MCP
        state = await SessionStateManager.set_workflow(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            workflow=WorkflowType.MCP,
            metadata={"mcp_server": "http://mock-mcp:8000", "tool": "run_diagnostic"}
        )
        self.assertEqual(state.active_workflow, WorkflowType.MCP)
        self.assertEqual(state.workflow_metadata["tool"], "run_diagnostic")

        # Update metadata
        state = await SessionStateManager.update_metadata(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            updates={"account_id": "ACC-12345"}
        )
        self.assertEqual(state.workflow_metadata["account_id"], "ACC-12345")

        # Reset to IDLE
        state = await SessionStateManager.reset_to_idle(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id
        )
        self.assertEqual(state.active_workflow, WorkflowType.IDLE)
        self.assertEqual(state.workflow_metadata, {})


class TestWorkflowRouter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tenant_id = 999
        self.conversation_id = "test-conv-router-001"

    @patch("app.orchestrator.router.SessionStateManager.get_state")
    @patch("app.orchestrator.router.SessionStateManager.reset_to_idle")
    async def test_cancellation_of_active_workflow(self, mock_reset, mock_get):
        active_mcp_state = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.MCP,
            workflow_metadata={"pending_tool": "verify_otp"}
        )
        mock_get.return_value = active_mcp_state
        mock_reset.return_value = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.IDLE
        )

        decision = await WorkflowRouter.route(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            message="cancel please"
        )
        self.assertEqual(decision.workflow, WorkflowType.IDLE)
        mock_reset.assert_called_once_with(self.tenant_id, self.conversation_id)

    @patch("app.orchestrator.router.SessionStateManager.get_state")
    async def test_continuation_of_active_mcp_workflow(self, mock_get):
        active_mcp_state = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.MCP,
            workflow_metadata={"pending_tool": "verify_otp"}
        )
        mock_get.return_value = active_mcp_state

        decision = await WorkflowRouter.route(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            message="My OTP code is 482910"
        )
        self.assertEqual(decision.workflow, WorkflowType.MCP)
        self.assertTrue(decision.is_continuation)

    @patch("app.orchestrator.router.SessionStateManager.get_state")
    async def test_continuation_of_active_form_workflow(self, mock_get):
        active_form_state = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.FORM_COLLECTION,
            workflow_metadata={"missing_fields": ["phone"]}
        )
        mock_get.return_value = active_form_state

        decision = await WorkflowRouter.route(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            message="Phone number is 9841234567"
        )
        self.assertEqual(decision.workflow, WorkflowType.FORM_COLLECTION)
        self.assertTrue(decision.is_continuation)

    @patch("app.orchestrator.router.SessionStateManager.get_state")
    @patch("app.orchestrator.router.SessionStateManager.set_workflow")
    async def test_direct_human_escalation(self, mock_set, mock_get):
        idle_state = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.IDLE
        )
        mock_get.return_value = idle_state
        mock_set.return_value = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.HUMAN_ESCALATION
        )

        decision = await WorkflowRouter.route(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            message="I want to talk to a human agent immediately"
        )
        self.assertEqual(decision.workflow, WorkflowType.HUMAN_ESCALATION)
        mock_set.assert_called_once()

    @patch("app.orchestrator.router.SessionStateManager.get_state")
    @patch("app.orchestrator.router.SessionStateManager.set_workflow")
    @patch("app.orchestrator.router.WorkflowRouter._classify_intent_llm")
    async def test_new_mcp_intent_routing(self, mock_classify, mock_set, mock_get):
        idle_state = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.IDLE
        )
        mock_get.return_value = idle_state
        mock_classify.return_value = (WorkflowType.MCP, 0.96, "Diagnostic tool requested")
        mock_set.return_value = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.MCP
        )

        decision = await WorkflowRouter.route(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            message="My internet fiber is red, run diagnostic on account 98410"
        )
        self.assertEqual(decision.workflow, WorkflowType.MCP)
        self.assertFalse(decision.is_continuation)
        mock_set.assert_called_once_with(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            workflow=WorkflowType.MCP
        )

    @patch("app.orchestrator.router.SessionStateManager.get_state")
    @patch("app.orchestrator.router.SessionStateManager.save_state")
    @patch("app.orchestrator.router.WorkflowRouter._classify_intent_llm")
    async def test_rag_intent_routing(self, mock_classify, mock_save, mock_get):
        idle_state = SessionState(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            active_workflow=WorkflowType.IDLE
        )
        mock_get.return_value = idle_state
        mock_classify.return_value = (WorkflowType.RAG, 0.92, "General FAQ question")

        decision = await WorkflowRouter.route(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            message="What are your office hours in Lalitpur?"
        )
        self.assertEqual(decision.workflow, WorkflowType.RAG)
        self.assertFalse(decision.is_continuation)


if __name__ == "__main__":
    unittest.main()

