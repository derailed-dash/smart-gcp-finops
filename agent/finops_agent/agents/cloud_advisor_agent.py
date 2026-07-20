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
from finops_agent.client import ConfiguredGemini
from finops_agent.config import settings

CLOUD_ADVISOR_INSTRUCTION = """You are the CloudAdvisor subagent.
Use Gemini Cloud Assist tools (ask_cloud_assist) to retrieve active rightsizing recommendations and performance/cost optimizations for active GCP resources.

CRITICAL AUTH/PERMISSION RULE:
If any call to a Gemini Cloud Assist tool returns a "403", "Forbidden", "Permission Denied", or authentication/authorization error:
You MUST NOT retry the call. You MUST immediately stop calling the tool, and invoke the `finish_task` tool with a report stating that cost optimization recommendations could not be retrieved due to insufficient project permissions (403 Forbidden) for that project.

CRITICAL COORDINATION AND TERMINATION RULES:
1. When calling the `finish_task` tool, you MUST pass the **complete final markdown report** (including all recommendations and optimization guides, or the permission error report) directly into the `result` parameter. Do NOT pass a brief summary or status message (like "Task complete"). The parent root coordinator is completely blind to your internal chat stream and relies entirely on the string returned in the `result` parameter of `finish_task` to receive your output.
2. Once you have generated the report and returned it via `finish_task`, stop execution immediately.
"""

cloud_advisor = Agent(
    name="cloud_advisor",
    description="Specialized subagent that calls Gemini Cloud Assist tools to retrieve active rightsizing recommendations and performance/cost optimizations for active GCP resources.",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=CLOUD_ADVISOR_INSTRUCTION + BLACKBOARD_KEY_INSTRUCTIONS,
    tools=[
        cloud_assist_mcp_toolset,
        get_session_value,
    ],
    mode="task",
)
