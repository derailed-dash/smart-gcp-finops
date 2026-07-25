"""Model Context Protocol (MCP) toolsets and OAuth2 auth providers.

What:
    Configures MCP toolsets (such as Developer Knowledge and Gemini Cloud Assist) and authentication handlers
    for use by the ADK agent.

Why:
    Extends the agent's knowledge and diagnostic capabilities with external MCP servers while ensuring secure,
    refreshed OAuth2 token handling.

How:
    Defines custom OAuth2 header providers (e.g. ``GcpMcpAuthProvider``) and instantiates ADK ``McpToolset``
    instances configured with HTTP stream connection parameters.
"""

import logging
import threading

import google.auth
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.auth.transport.requests import Request

from finops_agent.config import settings

logger = logging.getLogger(__name__)


class GcpMcpAuthProvider:
    """Provides valid OAuth2 headers for Google Cloud remote MCP connections."""

    def __init__(self, scopes: list[str] | None = None):
        self._scopes = scopes or ["https://www.googleapis.com/auth/cloud-platform"]
        self._credentials = None
        self._lock = threading.Lock()

    def __call__(self, ctx: ReadonlyContext) -> dict[str, str]:
        with self._lock:
            if self._credentials is None:
                self._credentials, _ = google.auth.default(scopes=self._scopes)

            if not self._credentials.valid:
                self._credentials.refresh(Request())

            token = self._credentials.token

        return {
            "Authorization": f"Bearer {token}",
            "x-goog-user-project": settings.google_cloud_project,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }


# Developer Knowledge MCP Toolset Configuration
dev_knowledge_mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://developerknowledge.googleapis.com/mcp",
    ),
    header_provider=GcpMcpAuthProvider(),
)


# Gemini Cloud Assist MCP Toolset Configuration
cloud_assist_mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://geminicloudassist.googleapis.com/mcp",
    ),
    header_provider=GcpMcpAuthProvider(),
)
