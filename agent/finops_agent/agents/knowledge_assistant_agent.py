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

GUIDELINES:
1. Identify the specific GCP services provided in the user prompt or identified as top cost drivers (e.g. Vertex AI, Gemini API, BigQuery, Cloud Storage).
2. Query the Developer Knowledge MCP to find official Google Cloud cost optimization strategies, architectural patterns, quota management, lifecycle policies, and scaling guidelines for those specific services.
3. Always provide inline citations referencing official GCP documentation when presenting architectural advice or product recommendations.
4. When outputting references or citations, ALWAYS format them as standard single-line Markdown links: [Title](URL). Never insert line breaks or whitespace inside the URL or between `]` and `(`.
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
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=False,
)
