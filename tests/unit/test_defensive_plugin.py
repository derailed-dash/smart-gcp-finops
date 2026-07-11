from unittest.mock import MagicMock

import pytest
from finops_agent.agent import DefensiveToolErrorPlugin, before_model_bypass
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool, ToolContext


@pytest.mark.asyncio
async def test_defensive_tool_error_plugin():
    """Verify that DefensiveToolErrorPlugin intercepts tool exceptions and saves them to state."""
    plugin = DefensiveToolErrorPlugin()
    tool = MagicMock(spec=BaseTool)
    tool.name = "test_tool"

    # Setup ToolContext mock with state dictionary
    tool_context = MagicMock(spec=ToolContext)
    tool_context.state = {}

    error = ValueError("Database connection failed")

    # Call the plugin's error callback
    result = await plugin.on_tool_error_callback(
        tool=tool,
        tool_args={"arg1": "val1"},
        tool_context=tool_context,
        error=error,
    )

    # Assertions
    assert result == {"error": "Database connection failed"}
    assert "last_tool_error" in tool_context.state
    assert tool_context.state["last_tool_error"] == {
        "tool": "test_tool",
        "error": "Database connection failed",
    }


@pytest.mark.asyncio
async def test_before_model_bypass_cached_response():
    """Verify that before_model_bypass immediately returns cached response if present."""
    callback_context = MagicMock(spec=CallbackContext)
    callback_context.state = {"cached_agent_response": "Hello cached world!"}
    callback_context.user_id = "test-user@example.com"

    response = await before_model_bypass(callback_context)

    assert isinstance(response, LlmResponse)
    assert response.content.parts[0].text == "Hello cached world!"


@pytest.mark.asyncio
async def test_before_model_bypass_unauthenticated():
    """Verify that before_model_bypass halts with access denied if user_id is missing."""
    callback_context = MagicMock(spec=CallbackContext)
    callback_context.state = {}
    callback_context.user_id = None

    response = await before_model_bypass(callback_context)

    assert isinstance(response, LlmResponse)
    assert "Access Denied" in response.content.parts[0].text
    assert "Unauthenticated request" in response.content.parts[0].text


@pytest.mark.asyncio
async def test_before_model_bypass_unauthorized_zero_projects():
    """Verify that before_model_bypass halts with access denied if user has 0 allowed projects."""
    callback_context = MagicMock(spec=CallbackContext)
    callback_context.state = {"allowed_projects": []}
    callback_context.user_id = "test-user@example.com"

    response = await before_model_bypass(callback_context)

    assert isinstance(response, LlmResponse)
    assert "Access Denied" in response.content.parts[0].text
    assert "does not have access to any GCP projects" in response.content.parts[0].text


@pytest.mark.asyncio
async def test_before_model_bypass_tool_error():
    """Verify that before_model_bypass halts with error message if last_tool_error is in state."""
    callback_context = MagicMock(spec=CallbackContext)
    callback_context.state = {
        "allowed_projects": ["proj-1"],
        "last_tool_error": {
            "tool": "execute_cached_bigquery_sql",
            "error": "400 Unrecognized name: _PARTITIONTIME",
        },
    }
    callback_context.user_id = "test-user@example.com"

    response = await before_model_bypass(callback_context)

    assert isinstance(response, LlmResponse)
    assert "Cost Analysis Execution Error" in response.content.parts[0].text
    assert "execute_cached_bigquery_sql" in response.content.parts[0].text
    assert "400 Unrecognized name: _PARTITIONTIME" in response.content.parts[0].text

    # Verify it popped the error from state to prevent infinite halts on next interactions
    assert "last_tool_error" not in callback_context.state


@pytest.mark.asyncio
async def test_before_model_bypass_no_interrupt():
    """Verify that before_model_bypass returns None (no bypass) if all conditions are healthy."""
    callback_context = MagicMock(spec=CallbackContext)
    callback_context.state = {"allowed_projects": ["proj-1"]}
    callback_context.user_id = "test-user@example.com"

    response = await before_model_bypass(callback_context)

    assert response is None
