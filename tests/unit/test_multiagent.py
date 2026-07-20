"""
Description: Unit tests for orchestrator subagent registration, configurations, and state sharing.
Why: Ensures the multi-agent graph, dispatch routing rules, and inter-agent context sharing behave correctly.
"""

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


def test_subagent_prompts_have_no_unresolved_placeholders():
    """Verify that subagent system instructions do not contain raw unescaped curly brace placeholders.
    Any placeholder `{key}` that isn't escaped as `{{key}}` or marked as optional (`{key?}`)
    will raise a KeyError at runtime.
    """
    import re
    import string
    subagents = root_agent.sub_agents
    formatter = string.Formatter()

    # Pattern matches standard python variables, optionally ending in '?'
    var_pattern = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*\??$")

    for sa in subagents:
        if not sa.instruction:
            continue
        parsed = list(formatter.parse(sa.instruction))
        for _, field_name, _, _ in parsed:
            if field_name is not None:
                # Strip spaces and verify if it matches a valid variable name
                clean_field = field_name.strip()
                if var_pattern.match(clean_field):
                    # Optional parameters in ADK template engine end with '?'
                    assert clean_field.endswith("?"), (
                        f"Subagent '{sa.name}' instruction has unescaped template placeholder: "
                        f"'{clean_field}'. Either escape it as '{{{{{clean_field}}}}}' or make it "
                        f"optional by appending '?' (e.g., '{{{clean_field}?}}') to prevent runtime KeyErrors."
                    )


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


def test_inter_agent_state_sharing():
    """Verify that cached objects in session state can be shared and read between different agents' contexts."""
    import time
    from unittest.mock import MagicMock, patch

    from finops_agent.app_utils.zombie_tools import list_zombie_resources
    from google.adk.tools import ToolContext

    # Initialize a single, shared session state dictionary
    shared_state = {
        "allowed_projects": ["test-project"],
        "zombies_UNATTACHED_DISKS_None": (time.time() + 300, [{"name": "shared_zombie_disk"}])
    }

    # Simulate Agent 1 (InfrastructureAuditor) using ToolContext linked to the shared state
    ctx_agent1 = MagicMock(spec=ToolContext)
    ctx_agent1.state = shared_state
    ctx_agent1.user_id = "test-user"

    # Simulate Agent 2 (BillingExplorer) using a separate ToolContext but sharing the exact same state reference
    ctx_agent2 = MagicMock(spec=ToolContext)
    ctx_agent2.state = shared_state
    ctx_agent2.user_id = "test-user"

    # Verify Agent 2 hits the session cache set by Agent 1 (or manually injected) without running any query
    with patch("finops_agent.app_utils.zombie_tools.search_zombie_resources") as mock_search:
        results = list_zombie_resources(
            category="UNATTACHED_DISKS",
            project_id=None,
            tool_context=ctx_agent2
        )
        assert len(results) == 1
        assert results[0]["name"] == "shared_zombie_disk"
        mock_search.assert_not_called()


def test_blackboard_get_set_session_value():
    """Verify that get_session_value and set_session_value correctly read and write custom keys in the shared ToolContext state."""
    from unittest.mock import MagicMock

    from finops_agent.app_utils.tools import get_session_value, set_session_value
    from google.adk.tools import ToolContext

    shared_state = {}
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = shared_state

    # 1. Initially get should return None
    assert get_session_value("gcs_secret_waste", mock_context) is None

    # 2. Set the value
    sample_waste = [{"resource": "bucket-1", "cost": 12.50}]
    set_res = set_session_value("gcs_secret_waste", sample_waste, mock_context)
    assert "Successfully stored" in set_res
    assert shared_state["gcs_secret_waste"] == sample_waste

    # 3. Get should now return the stored value
    retrieved = get_session_value("gcs_secret_waste", mock_context)
    assert retrieved == sample_waste


def test_subagent_instructions_have_blackboard_naming_standards():
    """Verify that all subagents have the central BLACKBOARD_KEY_INSTRUCTIONS appended to their instructions."""
    from finops_agent.agents.billing_explorer_agent import billing_explorer
    from finops_agent.agents.cloud_advisor_agent import cloud_advisor
    from finops_agent.agents.infrastructure_auditor_agent import infrastructure_auditor
    from finops_agent.agents.root_cause_analyst_agent import root_cause_analyst
    from finops_agent.app_utils.tools import BLACKBOARD_KEY_INSTRUCTIONS

    for agent in [billing_explorer, infrastructure_auditor, cloud_advisor, root_cause_analyst]:
        assert BLACKBOARD_KEY_INSTRUCTIONS in agent.instruction, (
            f"Subagent {agent.name} is missing the shared BLACKBOARD_KEY_INSTRUCTIONS naming standards."
        )


def test_blackboard_dynamic_key_lookups():
    """Verify that all standard blackboard keys can be dynamically written and read from the shared state."""
    from unittest.mock import MagicMock

    from finops_agent.app_utils.tools import get_session_value, set_session_value
    from google.adk.tools import ToolContext

    shared_state = {}
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = shared_state

    keys_to_test = [
        ("daily_service_costs_30d", [{"date": "2026-07-18", "cost": 100.0}]),
        ("sku_period_costs_60d", [{"sku": "SKU-1", "cost": 50.0}]),
        ("gcs_secret_waste", [{"bucket": "b-1", "cost": 5.0}]),
        ("zombie_resources", [{"resource": "disk-1", "type": "disk"}]),
        ("rightsizing_recommendations", [{"rec": "rightsize Cloud Run", "savings": 20.0}]),
    ]

    for key, value in keys_to_test:
        assert get_session_value(key, mock_context) is None
        set_session_value(key, value, mock_context)
        assert get_session_value(key, mock_context) == value



