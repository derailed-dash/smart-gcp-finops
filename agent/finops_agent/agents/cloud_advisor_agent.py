"""
Description: CloudAdvisor subagent definition.
Why: Requests operational and architectural rightsizing recommendations for active resources.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.mcp_config import cloud_assist_mcp_toolset
from finops_agent.client import ConfiguredGemini
from finops_agent.config import settings

CLOUD_ADVISOR_INSTRUCTION = """You are the CloudAdvisor subagent.
Use Gemini Cloud Assist tools (ask_cloud_assist) to retrieve active rightsizing recommendations and performance/cost optimizations for active GCP resources.

Provide clear, actionable recommendations to improve performance or reduce cloud spend based on the metrics and recommendation metadata retrieved from Cloud Assist.
"""

cloud_advisor = Agent(
    name="cloud_advisor",
    description="Specialized subagent that calls Gemini Cloud Assist tools to retrieve active rightsizing recommendations and performance/cost optimizations for active GCP resources.",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=CLOUD_ADVISOR_INSTRUCTION,
    tools=[
        cloud_assist_mcp_toolset,
    ],
    mode="task",
)
