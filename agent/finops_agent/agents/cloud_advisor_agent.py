"""
Description: CloudAdvisor subagent definition.
Why: Requests operational and architectural rightsizing recommendations for active resources.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.mcp_config import cloud_assist_mcp_toolset
from finops_agent.app_utils.tools import (
    COMMON_AGENT_HEADER,
    get_session_value,
)
from finops_agent.app_utils.typing import TaskOutput
from finops_agent.client import ConfiguredGemini
from finops_agent.config import settings

CLOUD_ADVISOR_INSTRUCTION = """You are the CloudAdvisor subagent.
Use Gemini Cloud Assist tools (ask_cloud_assist, investigate_issue) to retrieve active rightsizing recommendations, perform operational issue diagnostics, and optimize performance/cost for active GCP resources.

CRITICAL OPERATIONAL DIAGNOSIS & RIGHTSIGHTING RULES:
1. OPERATIONAL ANOMALIES: If the session context or prompt indicates active operational errors (e.g. `today_operational_anomaly == True` or crash loops), use `investigate_issue` or `ask_cloud_assist` to query active GCP Monitoring alerts, failing services, and system diagnostics for the affected project/service.
2. DISCOVERED CONTEXT: BEFORE querying, inspect the prompt and session context for the top active services and projects ALREADY DISCOVERED in this session.
3. Focus all recommendation and diagnostic queries (`ask_cloud_assist`, `investigate_issue`) SPECIFICALLY on those identified active services and projects.
4. Do NOT output generic boilerplate recommendations for unconfigured services (like GKE or Compute Engine VMs if they are not driving spend). Every recommendation MUST be tailored directly to the discovered active workloads.

CRITICAL AUTH & FALLBACK RULES:
1. If `ask_cloud_assist` returns recommendations or diagnostic findings, compile them into a clear, structured report detailing estimated monthly savings or operational remediation steps.
2. If `ask_cloud_assist` returns a 403 Forbidden or permission error for certain projects:
   - Highlight any recommendations retrieved from accessible active projects.
   - For projects lacking Recommender permissions, provide high-value, actionable optimization guidance strictly tailored to the specific active services discovered in the environment.
3. Always invoke `finish_task` with your complete, formatted Markdown report in the `result` argument.
"""

cloud_advisor = Agent(
    name="cloud_advisor",
    description="Specialized subagent that calls Gemini Cloud Assist tools to retrieve active rightsizing recommendations, perform operational issue diagnostics, and optimize performance/cost for active GCP resources.",
    model=ConfiguredGemini(
        model=settings.fast_model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=COMMON_AGENT_HEADER + "\n\n" + CLOUD_ADVISOR_INSTRUCTION,
    tools=[
        cloud_assist_mcp_toolset,
        get_session_value,
    ],
    mode="task",
    output_schema=TaskOutput,
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=False,
)
