"""
Description: CloudAdvisor subagent definition.
Why: Requests operational and architectural rightsizing recommendations for active resources.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.mcp_config import cloud_assist_mcp_toolset
from finops_agent.app_utils.tools import (
    BLACKBOARD_KEY_INSTRUCTIONS,
    get_session_value,
)
from finops_agent.app_utils.typing import TaskOutput
from finops_agent.client import ConfiguredGemini
from finops_agent.config import settings

CLOUD_ADVISOR_INSTRUCTION = """You are the CloudAdvisor subagent.
Use Gemini Cloud Assist tools (ask_cloud_assist) to retrieve active rightsizing recommendations and performance/cost optimizations for active GCP resources.

CRITICAL DISCOVERED CONTEXT & TAILORED AUDIT RULE:
1. BEFORE querying, inspect the prompt and conversation context for the top active services and projects ALREADY DISCOVERED in this session (e.g., Vertex AI in finops-admin-dev, Gemini API in finops-admin-prd, BigQuery).
2. Focus all recommendation queries (`ask_cloud_assist`) and optimization guidance SPECIFICALLY on those identified active services and projects.
3. Do NOT output generic boilerplate recommendations for unconfigured services (like GKE or Compute Engine VMs if they are not driving spend). Every optimization recommendation MUST be tailored directly to the discovered active workloads (e.g. Vertex AI endpoint auto-scaling, model batching, Gemini API context caching, BigQuery slot allocation).

CRITICAL AUTH & FALLBACK RULES:
1. If `ask_cloud_assist` returns recommendations, compile them into a clear, structured report detailing estimated monthly savings and actionable configuration changes for the identified services.
2. If `ask_cloud_assist` returns a 403 Forbidden or permission error for certain projects:
   - Highlight any recommendations retrieved from accessible active projects.
   - For projects lacking Recommender permissions, provide high-value, actionable optimization guidance strictly tailored to the specific active services discovered in the environment.
3. Always invoke `finish_task` with your complete, formatted Markdown report in the `result` argument.
"""

cloud_advisor = Agent(
    name="cloud_advisor",
    description="Specialized subagent that calls Gemini Cloud Assist tools to retrieve active rightsizing recommendations and performance/cost optimizations for active GCP resources.",
    model=ConfiguredGemini(
        model=settings.fast_model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=CLOUD_ADVISOR_INSTRUCTION + BLACKBOARD_KEY_INSTRUCTIONS,
    tools=[
        cloud_assist_mcp_toolset,
        get_session_value,
    ],
    mode="task",
    output_schema=TaskOutput,
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=False,
)
