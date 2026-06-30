"""
Description: Model Context Protocol (MCP) toolsets and authentication providers.
Why: Isolates MCP server configurations and authorisation loops from agent orchestration.
How: Uses `google-adk` to define and configure MCP toolsets for BigQuery and Developer Knowledge.
"""

import logging
import threading

import google.auth
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.auth.transport.requests import Request

from app.config import settings

logger = logging.getLogger(__name__)



class DevKnowledgeAuthProvider:
    """Provides valid OAuth2 headers for the Developer Knowledge MCP connection."""

    def __init__(self):
        self._credentials = None
        self._lock = threading.Lock()

    def __call__(self, ctx: ReadonlyContext) -> dict[str, str]:
        with self._lock:
            if self._credentials is None:
                self._credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )

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
    header_provider=DevKnowledgeAuthProvider(),
)


class CloudAssistAuthProvider:
    """Provides valid OAuth2 headers for the Gemini Cloud Assist MCP connection."""

    def __init__(self):
        self._credentials = None
        self._lock = threading.Lock()

    def __call__(self, ctx: ReadonlyContext) -> dict[str, str]:
        with self._lock:
            if self._credentials is None:
                self._credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )

            if not self._credentials.valid:
                self._credentials.refresh(Request())

            token = self._credentials.token

        return {
            "Authorization": f"Bearer {token}",
            "x-goog-user-project": settings.google_cloud_project,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }


# Gemini Cloud Assist MCP Toolset Configuration
cloud_assist_mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://geminicloudassist.googleapis.com/mcp",
    ),
    header_provider=CloudAssistAuthProvider(),
)
