from finops_agent.agent import root_agent


def test_coordinator_has_subagents():
    """Assert that the root agent (FinOpsCoordinator) has subagents registered."""
    subagents = root_agent.sub_agents
    assert len(subagents) > 0, "Coordinator must have subagents registered"

    subagent_names = [sa.name for sa in subagents]
    assert "billing_explorer" in subagent_names
    assert "infrastructure_auditor" in subagent_names
