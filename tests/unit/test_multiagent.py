import pytest
from finops_agent.agent import root_agent


def test_coordinator_has_all_five_subagents():
    """Assert that the root agent (FinOpsCoordinator) has all 5 subagents registered."""
    subagents = root_agent.sub_agents
    assert len(subagents) == 5, "Coordinator must have exactly 5 subagents registered"

    subagent_names = {sa.name for sa in subagents}
    expected_names = {
        "billing_explorer",
        "infrastructure_auditor",
        "cloud_advisor",
        "knowledge_assistant",
        "root_cause_analyst",
    }
    assert subagent_names == expected_names, f"Expected {expected_names}, got {subagent_names}"


def test_subagents_have_correct_modes_and_interactions_config():
    """Verify each subagent is instantiated with the correct mode and has interactions API disabled."""
    subagents_dict = {sa.name: sa for sa in root_agent.sub_agents}

    # Modes
    assert subagents_dict["billing_explorer"].mode == "task"
    assert subagents_dict["infrastructure_auditor"].mode == "task"
    assert subagents_dict["cloud_advisor"].mode == "task"
    assert subagents_dict["knowledge_assistant"].mode == "single_turn"
    assert subagents_dict["root_cause_analyst"].mode == "task"

    # use_interactions_api must be False for all subagents
    for name, sa in subagents_dict.items():
        assert sa.model.use_interactions_api is False, (
            f"Subagent {name} must have use_interactions_api set to False"
        )


def test_coordinator_exposes_no_direct_domain_tools():
    """Verify the coordinator (root agent) has no direct BQ or CAI tools in its tools list."""
    tool_names = {getattr(t, "__name__", str(t)) for t in root_agent.tools}

    # The coordinator should only delegate to subagents.
    # It must not contain BQ execution, BQ toolset, CAI zombie lists, etc.
    forbidden_tools = {
        "execute_cached_bigquery_sql",
        "bigquery_toolset",
        "list_zombie_resources",
        "get_cai_metadata_for_resources",
        "get_cai_history_for_resource",
        "ask_cloud_assist",
        "answer_query",
        "search_documents",
    }

    intersecting = tool_names.intersection(forbidden_tools)
    assert not intersecting, f"Coordinator must not contain direct domain tools: {intersecting}"


@pytest.mark.asyncio
async def test_telemetry_plugin_callbacks():
    """Verify FinOpsTelemetryPlugin callbacks run successfully without throwing attribute errors."""
    from unittest.mock import MagicMock

    from finops_agent.callbacks import FinOpsTelemetryPlugin
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.models.llm_request import LlmRequest

    plugin = FinOpsTelemetryPlugin()

    mock_agent = MagicMock()
    mock_agent.name = "test_agent"

    mock_session = MagicMock()
    mock_session.id = "test-session-123"

    mock_ctx = MagicMock(spec=CallbackContext)
    mock_ctx.session = mock_session
    mock_ctx.agent = mock_agent
    mock_ctx.node = mock_agent

    # Test before_agent_callback
    res_agent = await plugin.before_agent_callback(
        agent=mock_agent,
        callback_context=mock_ctx
    )
    assert res_agent is None

    # Test before_model_callback
    mock_request = MagicMock(spec=LlmRequest)
    mock_request.model = "gemini-3.5-flash"
    res_model = await plugin.before_model_callback(
        callback_context=mock_ctx,
        llm_request=mock_request
    )
    assert res_model is None
