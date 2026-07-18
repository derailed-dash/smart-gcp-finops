import pytest
from finops_agent.agent import root_agent
from google.adk.integrations.bigquery import BigQueryToolset
from google.adk.tools.mcp_tool import McpToolset


def test_agent_has_mcp_toolsets():
    """Verify that subagents are initialized with the correct McpToolsets."""
    subagents = {sa.name: sa for sa in root_agent.sub_agents}

    # CloudAdvisor should have the Cloud Assist McpToolset
    cloud_advisor_mcps = [t for t in subagents["cloud_advisor"].tools if isinstance(t, McpToolset)]
    assert len(cloud_advisor_mcps) == 1, "CloudAdvisor should have exactly one McpToolset"

    # KnowledgeAssistant should have the Developer Knowledge McpToolset
    knowledge_assistant_mcps = [t for t in subagents["knowledge_assistant"].tools if isinstance(t, McpToolset)]
    assert len(knowledge_assistant_mcps) == 1, "KnowledgeAssistant should have exactly one McpToolset"


@pytest.mark.asyncio
async def test_agent_has_native_bq_toolset():
    """Verify that the BillingExplorer is initialized with the native BigQueryToolset and query/execute tools are filtered out."""
    subagents = {sa.name: sa for sa in root_agent.sub_agents}
    bq_toolsets = [t for t in subagents["billing_explorer"].tools if isinstance(t, BigQueryToolset)]
    assert len(bq_toolsets) == 1, "BillingExplorer should have exactly one native BigQueryToolset"

    bq_toolset = bq_toolsets[0]
    # Check that tools returned by the toolset have query/execute filtered out
    tools = await bq_toolset.get_tools()
    for tool in tools:
        name = tool.name.lower()
        assert "execute" not in name, f"Tool {tool.name} should have been filtered out"
        assert "query" not in name, f"Tool {tool.name} should have been filtered out"


def test_agent_instruction_contains_billing_context():
    """Verify that the BillingExplorer instruction mentions the billing dataset."""
    subagents = {sa.name: sa for sa in root_agent.sub_agents}
    billing_explorer = subagents["billing_explorer"]
    assert "billing" in billing_explorer.instruction.lower()
    assert "dataset" in billing_explorer.instruction.lower()


def test_agent_has_cai_tools():
    """Verify that subagents are initialized with the correct CAI tools."""
    subagents = {sa.name: sa for sa in root_agent.sub_agents}

    infra_auditor_tools = [
        t.__name__ if hasattr(t, "__name__") else type(t).__name__ for t in subagents["infrastructure_auditor"].tools
    ]
    assert "get_cai_metadata_for_resources" in infra_auditor_tools, (
        "InfrastructureAuditor should have get_cai_metadata_for_resources tool"
    )

    rca_tools = [
        t.__name__ if hasattr(t, "__name__") else type(t).__name__ for t in subagents["root_cause_analyst"].tools
    ]
    assert "get_cai_history_for_resource" in rca_tools, (
        "RootCauseAnalyst should have get_cai_history_for_resource tool"
    )


def test_agent_instruction_contains_cai_context():
    """Verify that the subagent instructions mention the CAI tools."""
    subagents = {sa.name: sa for sa in root_agent.sub_agents}
    assert "get_cai_metadata_for_resources" in subagents["infrastructure_auditor"].instruction
    assert "get_cai_history_for_resource" in subagents["root_cause_analyst"].instruction


def test_agent_instruction_contains_developer_knowledge_context():
    """Verify that the subagent instruction mentions the Developer Knowledge tools."""
    subagents = {sa.name: sa for sa in root_agent.sub_agents}
    assert "developer knowledge" in subagents["knowledge_assistant"].instruction.lower()
