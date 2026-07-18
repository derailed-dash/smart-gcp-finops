"""
Description: Cross-cutting callback hooks and ADK plugins.
Why: Isolates telemetry, validation, and caching hooks from the agent orchestrator.
How: Subclasses `BasePlugin` and implements callback protocols from the ADK framework.
"""

import logging
import threading
import time
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools import BaseTool, ToolContext
from google.genai import types

from finops_agent.config import settings

logger = logging.getLogger(__name__)


class AgentQueryCacheManager:
    """Manages thread-safe in-memory caching of final agent text responses."""

    def __init__(self) -> None:
        self.query_cache: dict[str, tuple[float, str]] = {}
        self.cache_lock = threading.Lock()


# Module-level singleton instance for agent query caching
agent_query_cache_manager = AgentQueryCacheManager()

# Maintain direct module references pointing to manager attributes for unit test compatibility
_AGENT_QUERY_CACHE = agent_query_cache_manager.query_cache
_AGENT_CACHE_LOCK = agent_query_cache_manager.cache_lock

AGENT_CACHE_TTL = 300  # 5 minutes


async def before_agent_cache_lookup(callback_context: CallbackContext, **kwargs) -> None:
    """Uses a fast model to verify semantic query equivalence, skipping main agent execution on a match."""
    ctx = callback_context

    user_query = ""
    if ctx.session and hasattr(ctx.session, "events") and ctx.session.events:
        for event in reversed(ctx.session.events):
            if hasattr(event, "role") and event.role == "user":
                if (
                    hasattr(event, "content")
                    and event.content
                    and hasattr(event.content, "parts")
                    and event.content.parts
                ):
                    user_query = "".join(
                        part.text
                        for part in event.content.parts
                        if hasattr(part, "text") and part.text
                    )
                    break

    if not user_query:
        return

    now = time.time()
    active_keys = []
    with agent_query_cache_manager.cache_lock:
        expired_keys = [
            k for k, (expiry, _) in agent_query_cache_manager.query_cache.items() if now > expiry
        ]
        for ek in expired_keys:
            del agent_query_cache_manager.query_cache[ek]

        active_keys = list(agent_query_cache_manager.query_cache.keys())

    if not active_keys:
        return

    normalised_user = " ".join(user_query.strip().lower().split())
    local_match = None
    with agent_query_cache_manager.cache_lock:
        for k in active_keys:
            if " ".join(k.strip().lower().split()) == normalised_user:
                local_match = k
                break

    if local_match:
        with agent_query_cache_manager.cache_lock:
            if local_match in agent_query_cache_manager.query_cache:
                _, cached_text = agent_query_cache_manager.query_cache[local_match]
                logger.debug(
                    "🎯 Fast Local Cache HIT! Matched exact query '%s' to cached key '%s'",
                    user_query,
                    local_match,
                )
                ctx.state["cached_agent_response"] = cached_text
                return

    try:
        from finops_agent.agent import genai_client
        client = genai_client

        prompt = f"""You are a high-speed caching coordinator.
Your task is to determine if the user query is semantically identical or shares the exact same meaning as any of the cached queries listed below.
Minor differences in phrasing, word order, or punctuation should be matched. However, differences in timeframes (e.g., "last month" vs "last 90 days") or services should NOT be matched.

If a semantic match exists, reply ONLY with the exact matched cached query string from the list.
If no match exists, reply with 'NONE'. Do not include any other text or reasoning.

User Query: "{user_query}"

Cached Queries List:
{chr(10).join(f"- {k}" for k in active_keys)}
"""
        response = client.models.generate_content(
            model=settings.fast_model,
            contents=prompt,
        )

        matched_key = response.text.strip() if response.text else "NONE"
        matched_key = matched_key.strip("`'\" \n\r")

        if matched_key in agent_query_cache_manager.query_cache:
            _, cached_text = agent_query_cache_manager.query_cache[matched_key]
            logger.debug(
                "🎯 Semantic Cache HIT! Matched '%s' to cached key '%s'",
                user_query,
                matched_key,
            )

            ctx.state["cached_agent_response"] = cached_text
        else:
            logger.debug(
                "⚡ Cache Miss. No semantic equivalence found for: '%s' (LLM replied: '%s')",
                user_query,
                matched_key,
            )

    except Exception as e:
        logger.error("Failed to execute semantic cache lookup: %s", e)


class DefensiveToolErrorPlugin(BasePlugin):
    """Intercepts tool execution exceptions and stores them in session state to trigger a graceful halt."""

    def __init__(self, name: str = "defensive_tool_error_plugin"):
        super().__init__(name)

    async def on_tool_error_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        error: Exception,
    ) -> dict[str, Any] | None:
        logger.warning(
            "DefensiveToolErrorPlugin intercepted unhandled error in tool %s: %s",
            tool.name,
            error,
        )
        # Store error info in session state so before_model_bypass can intercept the next turn
        tool_context.state["last_tool_error"] = {
            "tool": tool.name,
            "error": str(error),
        }
        # Return a dictionary response to satisfy the runner, but it will be bypassed in the next turn
        return {"error": str(error)}


class FinOpsTelemetryPlugin(BasePlugin):
    """Global telemetry and tracing plugin for FinSavant.
    Logs agent handoffs and measures model invocations.
    """

    def __init__(self, name: str = "finops_telemetry_plugin"):
        super().__init__(name)

    async def before_agent_callback(
        self, *, agent: Any, callback_context: CallbackContext
    ) -> types.Content | None:
        session_id = callback_context.session.id if callback_context.session else "Unknown"
        logger.info(
            "FinOps Handoff: Entering agent '%s' with context session ID: %s",
            agent.name,
            session_id,
        )
        return None

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse | None:
        logger.info(
            "Model Invocation for agent: %s, model: %s",
            callback_context.node.name if callback_context.node else "Unknown",
            llm_request.model,
        )
        return None


def _override_llm_request_with_message(req: LlmRequest, message: str) -> None:
    """Safely overrides the LLM request to force the model to output a specific message verbatim,
    disabling all tool call capabilities and JSON output schema requirements.
    """
    req.contents = [
        types.Content(role="user", parts=[types.Part(text="Output the system warning message.")])
    ]
    req.config.system_instruction = (
        f"You must ignore all previous history and instructions. Immediately respond with the "
        f"following message verbatim and nothing else. Do not invoke any tools. Message:\n\n{message}"
    )
    req.config.tools = []
    req.config.response_schema = None
    req.config.response_mime_type = "text/plain"
    req.config.tool_config = None


async def before_model_bypass(
    callback_context: CallbackContext,
    request: LlmRequest | None = None,
    llm_request: LlmRequest | None = None,
    **kwargs,
) -> LlmResponse | None:
    """If a cached response is present, or if access is denied/tool fails, bypass the LLM entirely and return immediately."""
    ctx = callback_context
    req = llm_request or request

    # 1. Turn-level Cache lookup bypass
    if "cached_agent_response" in ctx.state:
        logger.debug("Bypassing ADK LLM call using cached agent response.")
        cached_msg = ctx.state["cached_agent_response"]
        if req:
            _override_llm_request_with_message(req, cached_msg)
            return None
        part = types.Part(text=cached_msg)
        content = types.Content(role="model", parts=[part])
        return LlmResponse(content=content)

    # 2. Defensive check: Authentication
    user_email = ctx.user_id
    if not user_email:
        logger.warning("Access denied inside before_model_bypass: missing user_id.")
        auth_msg = "❌ Access Denied: Unauthenticated request. Please sign in via Identity-Aware Proxy (IAP)."
        if req:
            _override_llm_request_with_message(req, auth_msg)
            return None
        part = types.Part(text=auth_msg)
        content = types.Content(role="model", parts=[part])
        return LlmResponse(content=content)

    # 3. Defensive check: Authorization (No projects linked or allowed)
    allowed_projects = ctx.state.get("allowed_projects")
    if allowed_projects is not None and len(allowed_projects) == 0:
        logger.warning(
            "Access denied inside before_model_bypass: user %s has no allowed projects.", user_email
        )
        auth_msg = (
            f"❌ Access Denied: The user `{user_email}` does not have access to any GCP projects "
            f"linked to the billing account `{settings.google_cloud_billing_account}`.\n\n"
            f"Please contact your administrator to verify that your account has been assigned "
            f"the appropriate project or billing viewer roles."
        )
        if req:
            _override_llm_request_with_message(req, auth_msg)
            return None
        part = types.Part(text=auth_msg)
        content = types.Content(role="model", parts=[part])
        return LlmResponse(content=content)

    # 4. Defensive check: Graceful halt on tool error
    if "last_tool_error" in ctx.state:
        error_info = ctx.state.pop("last_tool_error")
        logger.warning(
            "Graceful tool error intercept inside before_model_bypass: tool '%s' failed.",
            error_info["tool"],
        )
        friendly_msg = (
            f"❌ Cost Analysis Execution Error:\n"
            f"The tool `{error_info['tool']}` encountered an issue: `{error_info['error']}`.\n\n"
            f"Please modify your query or temporal filters and try again."
        )
        if req:
            _override_llm_request_with_message(req, friendly_msg)
            return None
        part = types.Part(text=friendly_msg)
        content = types.Content(role="model", parts=[part])
        return LlmResponse(content=content)

    return None


async def after_agent_save_cache(
    callback_context: CallbackContext, **kwargs
) -> types.Content | None:
    """Saves the final agent text response to the query cache for future turn-level caching."""
    ctx = callback_context
    if "cached_agent_response" in ctx.state:
        return None

    user_query = ""
    if ctx.session and hasattr(ctx.session, "events") and ctx.session.events:
        for event in reversed(ctx.session.events):
            if hasattr(event, "role") and event.role == "user":
                if (
                    hasattr(event, "content")
                    and event.content
                    and hasattr(event.content, "parts")
                    and event.content.parts
                ):
                    user_query = "".join(
                        part.text
                        for part in event.content.parts
                        if hasattr(part, "text") and part.text
                    )
                    break

    if not user_query:
        return None

    final_text = ""
    if ctx.session and hasattr(ctx.session, "events") and ctx.session.events:
        for event in reversed(ctx.session.events):
            if hasattr(event, "role") and event.role == "model" and event.content:
                if hasattr(event.content, "parts") and event.content.parts:
                    final_text = "".join(
                        part.text
                        for part in event.content.parts
                        if hasattr(part, "text") and part.text
                    )
                    break

    if user_query and final_text:
        now = time.time()
        with agent_query_cache_manager.cache_lock:
            agent_query_cache_manager.query_cache[user_query.strip()] = (
                now + AGENT_CACHE_TTL,
                final_text,
            )
        logger.debug("Saved agent response to ADK cache for query: %s", user_query)

    return None


async def reset_tool_call_counter(callback_context: CallbackContext, **kwargs) -> None:
    """Resets the tool call counter in session state at the start of each turn."""
    callback_context.state["_turn_tool_call_count"] = 0


async def discover_projects_callback(callback_context: CallbackContext, **kwargs) -> None:
    """Discovers allowed projects for the user up-front and caches them in session state."""
    state = callback_context.state
    if "allowed_projects" not in state:
        user_email = callback_context.user_id
        if user_email:
            from finops_agent.app_utils.project_discovery import (
                get_user_accessible_projects,
            )

            allowed_projects = get_user_accessible_projects(user_email)
            state["allowed_projects"] = list(allowed_projects)
            logger.info(
                "Discovered projects for user %s and stored in state: %s",
                user_email,
                state["allowed_projects"],
            )
        else:
            logger.warning(
                "Unauthenticated request inside discover_projects_callback: missing user_id."
            )
            state["allowed_projects"] = []


def check_tool_call_limit(tool: Any, args: dict[str, Any], tool_context: Any) -> None:
    """Defensive callback to count and limit tool calls in a single turn to prevent runaways."""
    count = tool_context.state.get("_turn_tool_call_count", 0) + 1
    tool_context.state["_turn_tool_call_count"] = count
    logger.debug(
        "Tool call #%d in this turn: executing %s with arguments: %s",
        count,
        tool.name,
        args,
    )
    if count > 25:
        logger.error("Defensive stop triggered: Tool call count exceeded limit of 25!")
        raise RuntimeError("Defensive stop: too many tool calls executed in a single turn.")
