from google.adk.tools.mcp_tool import McpToolset

from app.agent import root_agent


def test_agent_has_mcp_toolsets():
    """Verify that the agent is initialized with all three required McpToolsets."""
    mcp_toolsets = [t for t in root_agent.tools if isinstance(t, McpToolset)]
    assert len(mcp_toolsets) == 3, "Agent should have exactly three McpToolsets"


def test_agent_instruction_contains_billing_context():
    """Verify that the agent instruction mentions the billing dataset."""
    assert "billing" in root_agent.instruction.lower()
    assert "dataset" in root_agent.instruction.lower()


def test_agent_has_cai_tools():
    """Verify that the agent is initialized with the CAI tools."""
    tool_names = [
        t.__name__ if hasattr(t, "__name__") else type(t).__name__
        for t in root_agent.tools
    ]
    assert "get_cai_metadata_for_resources" in tool_names, (
        "Agent should have get_cai_metadata_for_resources tool"
    )
    assert "get_cai_history_for_resource" in tool_names, (
        "Agent should have get_cai_history_for_resource tool"
    )


def test_agent_instruction_contains_cai_context():
    """Verify that the agent instruction mentions the CAI tools."""
    assert "get_cai_metadata_for_resources" in root_agent.instruction
    assert "get_cai_history_for_resource" in root_agent.instruction


def test_agent_instruction_contains_developer_knowledge_context():
    """Verify that the agent instruction mentions the Developer Knowledge tools."""
    assert "developer knowledge" in root_agent.instruction.lower()
    assert "search_documents" in root_agent.instruction.lower()


def test_agent_instruction_contains_cloud_assist_context():
    """Verify that the agent instruction mentions the Cloud Assist tools and routing tree."""
    instruction_lower = root_agent.instruction.lower()
    assert "cloud assist" in instruction_lower
    assert "tool-routing decision tree" in instruction_lower
    assert "spend & historical trends" in instruction_lower
