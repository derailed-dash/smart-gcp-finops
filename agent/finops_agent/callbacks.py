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
        if tool.name == "detect_anomalies":
            logger.info(
                "Gracefully handling detect_anomalies failure by returning empty anomalies list."
            )
            return []

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
        log_level = settings.log_level.upper()
        if log_level == "DEBUG":
            logging.getLogger().setLevel(logging.DEBUG)
            logging.getLogger("finops_agent").setLevel(logging.DEBUG)
            logging.getLogger("google_adk").setLevel(logging.DEBUG)
            for handler in logging.getLogger().handlers:
                handler.setLevel(logging.DEBUG)

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
        agent_name = callback_context.agent_name or "Unknown"
        logger.debug(
            "Model Invocation for agent: %s, model: %s",
            agent_name,
            llm_request.model,
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Model Request Payload for agent '%s':\n%s",
                agent_name,
                llm_request,
            )
        return None

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> LlmResponse | None:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Model Response Payload for agent '%s':\n%s",
                callback_context.agent_name or "Unknown",
                llm_response,
            )
        return None

    async def before_tool_callback(
        self, *, tool: BaseTool, tool_context: ToolContext, **kwargs
    ) -> dict[str, Any] | None:
        if logger.isEnabledFor(logging.DEBUG):
            args = kwargs.get("tool_args") or kwargs.get("args") or {}
            logger.debug(
                "Tool Execution [%s] invoked:\nArguments: %s",
                tool.name,
                args,
            )
        return None

    async def after_tool_callback(
        self, *, tool: BaseTool, tool_context: ToolContext, **kwargs
    ) -> Any:
        tool_response = kwargs.get("tool_response")
        if logger.isEnabledFor(logging.DEBUG):
            args = kwargs.get("tool_args") or kwargs.get("args") or {}
            logger.debug(
                "Tool Execution [%s] completed:\nArguments: %s\nResult: %s",
                tool.name,
                args,
                tool_response,
            )
        return tool_response


async def before_model_bypass(
    callback_context: CallbackContext,
    **kwargs,
) -> LlmResponse | None:
    ctx = callback_context

    # 1. Turn-level Cache lookup bypass
    if "cached_agent_response" in ctx.state:
        logger.debug("Bypassing ADK LLM call using cached agent response.")
        cached_msg = ctx.state["cached_agent_response"]
        part = types.Part(text=cached_msg)
        content = types.Content(role="model", parts=[part])
        return LlmResponse(content=content)

    # 2. Defensive check: Authentication
    user_email = ctx.user_id
    if not user_email:
        logger.warning("Access denied inside before_model_bypass: missing user_id.")
        auth_msg = "❌ Access Denied: Unauthenticated request. Please sign in via Identity-Aware Proxy (IAP)."
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
        part = types.Part(text=auth_msg)
        content = types.Content(role="model", parts=[part])
        return LlmResponse(content=content)

    # 4. Defensive check: Graceful halt on tool error
    if "last_tool_error" in ctx.state:
        error_info = ctx.state["last_tool_error"]
        del ctx.state["last_tool_error"]
        logger.warning(
            "Graceful tool error intercept inside before_model_bypass: tool '%s' failed.",
            error_info["tool"],
        )
        friendly_msg = (
            f"❌ Cost Analysis Execution Error:\n"
            f"The tool `{error_info['tool']}` encountered an issue: `{error_info['error']}`.\n\n"
            f"Please modify your query or temporal filters and try again."
        )
        part = types.Part(text=friendly_msg)
        content = types.Content(role="model", parts=[part])
        return LlmResponse(content=content)

    # 5. Coordinator bypass: check if subagent response is consolidated or directly in history
    if ctx.agent_name == "root_agent" and ctx.session and ctx.session.events:
        last_ev = ctx.session.events[-1]

        # Scenario A: Check if consolidated directly into the user event
        if getattr(last_ev, "role", None) == "user" and last_ev.content and last_ev.content.parts:
            for part in last_ev.content.parts:
                if (
                    part.text
                    and "[Context: Subagent '" in part.text
                    and "' returned result:\n" in part.text
                ):
                    marker = "' returned result:\n"
                    idx = part.text.find(marker)
                    if idx != -1:
                        res_text = part.text[idx + len(marker) :]
                        if res_text.endswith("]"):
                            res_text = res_text[:-1]
                        if res_text.strip():
                            logger.info(
                                "Bypassing root_agent model call; passing through consolidated subagent response directly."
                            )
                            new_part = types.Part(text=res_text)
                            content = types.Content(role="model", parts=[new_part])
                            return LlmResponse(content=content)

        # Scenario B: Check if there's a subagent response event in the history
        resps = []
        if hasattr(last_ev, "get_function_responses"):
            resps = last_ev.get_function_responses()
        if not resps and last_ev.content and last_ev.content.parts:
            resps = [p.function_response for p in last_ev.content.parts if p.function_response]

        subagent_names = {
            "billing_explorer",
            "infrastructure_auditor",
            "cloud_advisor",
            "knowledge_assistant",
            "root_cause_analyst",
        }
        if resps and any(r.name in subagent_names for r in resps):
            for r in resps:
                if r.name in subagent_names:
                    resp_val = r.response
                    result_text = ""
                    if isinstance(resp_val, dict):
                        result_text = (
                            resp_val.get("result") or resp_val.get("output") or str(resp_val)
                        )
                    elif isinstance(resp_val, str):
                        result_text = resp_val
                    else:
                        result_text = str(resp_val)

                    if result_text:
                        logger.info(
                            "Bypassing root_agent model call; passing through subagent '%s' response directly.",
                            r.name,
                        )
                        new_part = types.Part(text=result_text)
                        content = types.Content(role="model", parts=[new_part])
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


async def clean_history_callback(callback_context: CallbackContext, **kwargs) -> None:
    """Cleans up the session history for the root coordinator:
    1. At the start of a user turn, removes previous turns' tool pollution.
    2. Mid-turn (when re-entered), strips subagents' internal tool calls/responses
       to prevent ADK history alignment crashes.
    """
    ctx = callback_context
    if not (ctx.session and hasattr(ctx.session, "events") and ctx.session.events):
        return

    events = ctx.session.events

    # Main subagent tool names registered on root_agent
    subagent_names = {
        "billing_explorer",
        "infrastructure_auditor",
        "cloud_advisor",
        "knowledge_assistant",
        "root_cause_analyst",
    }

    last_event = events[-1]

    # CASE 1: Start of a new user turn -> Clean up previous turns
    if getattr(last_event, "role", None) == "user":
        cleaned_events = []
        for i, ev in enumerate(events):
            # Always keep the last event (new user prompt)
            if i == len(events) - 1:
                cleaned_events.append(ev)
                continue

            role = getattr(ev, "role", None)
            if role == "user":
                cleaned_events.append(ev)
            elif role == "model":
                # Keep model responses only if they don't contain function calls
                has_fc = False
                if hasattr(ev, "get_function_calls") and ev.get_function_calls():
                    has_fc = True
                if not has_fc and ev.content and ev.content.parts:
                    if any(getattr(p, "text", None) for p in ev.content.parts):
                        cleaned_events.append(ev)

        logger.debug(
            "Start-of-turn cleanup for session %s: reduced to %d events.",
            ctx.session.id,
            len(cleaned_events),
        )
        ctx.session.events = cleaned_events
        return

    # CASE 2: Mid-turn re-entry -> Strip subagent internal tools (e.g. SQL queries, blackboard writes)
    cleaned_events = []
    for ev in events:
        is_internal_tool = False

        # Check function calls via helper method
        if hasattr(ev, "get_function_calls"):
            calls = ev.get_function_calls()
            if calls and any(c.name not in subagent_names for c in calls):
                is_internal_tool = True

        # Check function responses via helper method
        if hasattr(ev, "get_function_responses"):
            resps = ev.get_function_responses()
            if resps and any(r.name not in subagent_names for r in resps):
                is_internal_tool = True

        # Fallback check on content parts directly
        if not is_internal_tool and ev.content and ev.content.parts:
            for part in ev.content.parts:
                if part.function_call and part.function_call.name not in subagent_names:
                    is_internal_tool = True
                    break
                if part.function_response and part.function_response.name not in subagent_names:
                    is_internal_tool = True
                    break

        if not is_internal_tool:
            cleaned_events.append(ev)

    logger.debug(
        "Mid-turn cleanup for session %s: stripped internal subagent tools, reduced from %d to %d events.",
        ctx.session.id,
        len(events),
        len(cleaned_events),
    )

    # CASE 3: Consolidate subagent results into the preceding user prompt event
    # to maintain strict alternating roles (user -> model -> user).
    final_cleaned = []
    current_user_ev = None

    for ev in cleaned_events:
        # Keep track of the latest user prompt (not a tool response)
        if getattr(ev, "author", None) == "user":
            resps = ev.get_function_responses() if hasattr(ev, "get_function_responses") else []
            if not resps and ev.content and ev.content.parts:
                resps = [p.function_response for p in ev.content.parts if p.function_response]
            if not resps:
                current_user_ev = ev
                final_cleaned.append(ev)
                continue

        # Strip the empty coordinator model event (only if it has no calls and no text)
        if getattr(ev, "author", None) == "root_agent":
            calls = ev.get_function_calls() if hasattr(ev, "get_function_calls") else []
            if not calls and ev.content and ev.content.parts:
                calls = [p.function_call for p in ev.content.parts if p.function_call]
            has_text = False
            if ev.content and ev.content.parts:
                has_text = any(p.text and p.text.strip() for p in ev.content.parts)
            if not calls and not has_text:
                logger.debug("Stripped empty root_agent model event from history.")
                continue
            final_cleaned.append(ev)
            continue

        # Check if it's a subagent response
        resps = ev.get_function_responses() if hasattr(ev, "get_function_responses") else []
        if not resps and ev.content and ev.content.parts:
            resps = [p.function_response for p in ev.content.parts if p.function_response]

        is_subagent_resp = False
        subagent_name = None
        resp_data = None
        for resp in resps:
            r_name = getattr(resp, "name", None)
            if r_name in subagent_names:
                is_subagent_resp = True
                subagent_name = r_name
                resp_data = getattr(resp, "response", {})
                break

        if is_subagent_resp and subagent_name:
            # Extract task result markdown
            result_text = ""
            if isinstance(resp_data, dict):
                result_text = (
                    resp_data.get("task_result") or resp_data.get("result") or str(resp_data)
                )
            else:
                result_text = str(resp_data)

            # Consolidate directly into the preceding user prompt
            if current_user_ev and current_user_ev.content:
                if not current_user_ev.content.parts:
                    current_user_ev.content.parts = []
                current_user_ev.content.parts.append(
                    types.Part(
                        text=f"\n\n[Context: Subagent '{subagent_name}' returned result:\n{result_text}]"
                    )
                )
                logger.debug(
                    "Consolidated subagent '%s' result directly into user prompt event.",
                    subagent_name,
                )
            else:
                logger.warning(
                    "Could not find preceding user event to consolidate subagent response."
                )
            continue

        final_cleaned.append(ev)

    ctx.session.events = final_cleaned
