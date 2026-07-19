"""
Description: Agent orchestration and configuration.
Why: Defines the ADK coordinator agent and sets up the global ADK App.
How: Uses the `google-adk` SDK, registering the 5 subagents and plugins.
"""

import logging
import os
import sys

# Ensure the parent directory is in sys.path so that 'import finops_agent' resolves correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.agents import Agent
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps import App
from google.genai import types

from finops_agent.agents import (
    billing_explorer,
    cloud_advisor,
    infrastructure_auditor,
    knowledge_assistant,
    root_cause_analyst,
)
from finops_agent.callbacks import (
    DefensiveToolErrorPlugin,
    FinOpsTelemetryPlugin,
    after_agent_save_cache,
    before_agent_cache_lookup,
    before_model_bypass,
    check_tool_call_limit,
    clean_history_callback,
    discover_projects_callback,
    reset_tool_call_counter,
)

# Expose shared variables and models for other parts of the application
from finops_agent.client import (
    ConfiguredGemini,
    genai_client,  # noqa: F401
)
from finops_agent.config import settings

logger = logging.getLogger(__name__)

AGENT_INSTRUCTION = """You are the FinOpsCoordinator root agent.
Your primary role is to receive user requests, understand their intent, and delegate cost analysis, auditing, optimization, and Q&A tasks to the appropriate specialist subagents:

1. BillingExplorer: Use for spend aggregates, SKU prices, cost trends, forecasting, and Cost Explorer (explorer/dashboard) dashboards.
2. InfrastructureAuditor: Use for auditing zombie resources like idle static IPs or unattached disks (recommendations dashboard).
3. CloudAdvisor: Use for active GCP rightsizing and resource-level cost/performance optimizations.
4. KnowledgeAssistant: Use for general GCP Q&A and grounding recommendations in official architectural guidelines.
5. RootCauseAnalyst: Use for analyzing cost spikes by correlating BigQuery spend shifts with CAI configuration change history.

CRITICAL SELECTIVE ROUTING RULES:
1. You MUST only delegate tasks to the specific subagent(s) directly relevant to the user's request.
   - If the user only asks about costs, spend trends, SKU prices, or budgets, ONLY invoke BillingExplorer. Do NOT invoke CloudAdvisor or InfrastructureAuditor.
   - If the user only asks about rightsizing, active recommendations, or optimizations, ONLY invoke CloudAdvisor.
   - If the user only asks about zombie resources, idle IPs, or unattached disks, ONLY invoke InfrastructureAuditor.
2. Do NOT run a full multi-agent audit (calling multiple subagents) unless the user explicitly requests a "full audit", "comprehensive review", "complete environment analysis", or asks a multi-faceted question that spans multiple domains. Keep simple queries fast and single-scoped!
"""

root_agent = Agent(
    name="root_agent",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=AGENT_INSTRUCTION,
    tools=[],
    sub_agents=[
        billing_explorer,
        infrastructure_auditor,
        cloud_advisor,
        knowledge_assistant,
        root_cause_analyst,
    ],
    before_agent_callback=[
        clean_history_callback,
        reset_tool_call_counter,
        discover_projects_callback,
        before_agent_cache_lookup,
    ],
    before_tool_callback=check_tool_call_limit,
    before_model_callback=before_model_bypass,
    after_agent_callback=after_agent_save_cache,
)

app = App(
    root_agent=root_agent,
    name="finops_agent",
    context_cache_config=ContextCacheConfig(
        min_tokens=2048,  # Trigger caching for large prompts/histories on Vertex AI / Gemini
        ttl_seconds=600,  # Store the cache for up to 10 minutes
        cache_intervals=10,  # Refresh after 10 turns
    ),
    plugins=[DefensiveToolErrorPlugin(), FinOpsTelemetryPlugin()],
)
