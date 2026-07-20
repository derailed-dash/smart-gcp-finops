"""
Description: KnowledgeAssistant subagent definition.
Why: Grounds architectural best practices in official GCP guidelines and documentation.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.mcp_config import dev_knowledge_mcp_toolset
from finops_agent.client import ConfiguredGemini
from finops_agent.config import settings

KNOWLEDGE_ASSISTANT_INSTRUCTION = """You are the KnowledgeAssistant subagent.
Query the Developer Knowledge MCP to retrieve and ground cost optimization recommendations in official GCP architectural guidelines.

Always provide citations referencing official GCP documentation when presenting architectural advice or product recommendations.
"""

knowledge_assistant = Agent(
    name="knowledge_assistant",
    description="Specialized subagent that queries the Developer Knowledge MCP to retrieve and ground cost optimization recommendations in official GCP architectural guidelines and best practices.",
    model=ConfiguredGemini(
        model=settings.fast_model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=KNOWLEDGE_ASSISTANT_INSTRUCTION,
    tools=[
        dev_knowledge_mcp_toolset,
    ],
    mode="single_turn",
)
