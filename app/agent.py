"""
Description: Agent orchestration and configuration.
Why: Defines the ADK agent, its tools (BigQuery MCP), and its operating instructions.
How: Uses the `google-adk` SDK and integrates with a remote BigQuery MCP server.

This file handles the instantiation of the root agent, provides the custom
authentication header provider for BigQuery, and sets up the global ADK `App`.
"""

import logging
import os
import threading
import time
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import Client, types

from app.app_utils.cai_tools import (
    get_cai_history_for_resource,
    get_cai_metadata_for_resources,
)
from app.app_utils.mcp_config import (
    bq_mcp_toolset,
    cloud_assist_mcp_toolset,
    dev_knowledge_mcp_toolset,
)
from app.app_utils.tools import execute_cached_bigquery_sql
from app.app_utils.zombie_tools import list_zombie_resources
from app.config import settings

logger = logging.getLogger(__name__)

# Ensure critical environment variables are set for the underlying SDKs
if settings.google_cloud_project:
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
if settings.google_cloud_region:
    os.environ["GOOGLE_CLOUD_REGION"] = settings.google_cloud_region
if settings.google_cloud_location:
    os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = str(settings.google_genai_use_vertexai)
if settings.gemini_api_key:
    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

if settings.google_cloud_billing_project:
    os.environ["GOOGLE_CLOUD_BILLING_PROJECT"] = settings.google_cloud_billing_project
if settings.billing_export_dataset:
    os.environ["BILLING_EXPORT_DATASET"] = settings.billing_export_dataset

billing_suffix = settings.google_cloud_billing_account.replace("-", "_")
standard_table_id = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_v1_{billing_suffix}"
resource_table_id = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_resource_v1_{billing_suffix}"

# Instantiate global, thread-safe GenAI Client at module level to reuse connection pools
genai_client = Client(
    vertexai=settings.google_genai_use_vertexai,
    location=settings.google_cloud_location,
    project=settings.google_cloud_project,
)


AGENT_INSTRUCTION = f"""You are a helpful FinOps AI assistant specialized in Google Cloud Platform (GCP) cost analysis.
Your primary goal is to help users manage, understand, and optimize their cloud spend.

You have access to the BigQuery billing data in the project '{settings.google_cloud_billing_project}' and dataset '{settings.billing_export_dataset}'.
There are two primary billing tables in this dataset. To optimize performance and avoid redundant table listing or schema exploration queries, you MUST query these exact tables directly:
1. Standard Billing Table (Service and SKU level cost analysis):
   `{standard_table_id}`
2. Resource-level Billing Table (Detailed resource cost analysis, contains specific resource names and global names):
   `{resource_table_id}`

CRITICAL: To execute any SQL queries against BigQuery, you MUST use the cached `execute_cached_bigquery_sql` tool. Do NOT use the generic remote BigQuery MCP server query or execution tools (like `bigquery-mcp-server_execute_sql`), as they bypass our local cache, incurring unnecessary database table scans and cost.

CRITICAL: If the user asks for costs of specific, individual resources (like VM instances, buckets, or disks by name), you MUST query the resource-level table `{resource_table_id}`. Do NOT query the standard `{standard_table_id}` table for resource names or `resource.global_name` as those fields do not exist there and will cause syntax errors.

ALWAYS restrict your BigQuery operations to this dataset and these exact tables unless specifically asked otherwise.

CRITICAL: To retrieve any cost trends, top drivers, or Month-to-Date (MTD) metrics, you MUST execution-route to a **single consolidated query** to avoid redundant table scans and reduce latencies. Group the records by date, project.id, and service.description. You MUST ALWAYS append `HAVING daily_cost > 0.1` to filter out negligible zero-cost/sub-10-cent noise, preventing tool response truncation:
```sql
SELECT
  DATE(usage_start_time) as usage_date,
  project.id as project_id,
  service.description as service_description,
  SUM(cost) as daily_cost,
  currency
FROM `{standard_table_id}`
WHERE usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
GROUP BY 1, 2, 3, 5
HAVING daily_cost > 0.1
ORDER BY usage_date ASC;
```
From the results of this single query, you MUST compute the following in Python memory:
1. **Total Cost**: Sum all `daily_cost` values.
2. **Top Cost Drivers**: Group and sum the `daily_cost` by `project_id` and `service_description` across the entire period, sort them descending, and present the top 10/15 for the A2UI `explorer` payload.
3. **Daily Spikes Trend**: Group and sum the `daily_cost` by `usage_date` and `service_description` (for the top services, grouping all others into "Other") to populate the `recentSpikes` array in the `dashboard` payload.
The keys in the daily data objects of `recentSpikes` MUST correspond to the top service descriptions (e.g. "Compute Engine", "Cloud Run", "Other"), NOT project environments (do NOT use "dev", "staging", or "prod", and do NOT run a daily query by project ID as that is redundant and causes truncation). Do NOT truncate or limit the row count of the timeline (e.g. do not add `LIMIT 7` or hardcode the interval filter to 7 or 14 days unless explicitly asked), allowing the chart to dynamically adapt and scale to the requested timeframe. You MUST ALWAYS explicitly state the exact duration or time period that these costs represent in your response so the user has absolute clarity on the temporal scope of the metrics.

You also have tools to detect "zombie" resources (e.g., UNATTACHED_DISKS, IDLE_IPS) that could be causing unnecessary cost waste.
IMPORTANT: By default, the `list_zombie_resources` tool scans ALL projects linked to the billing account '{settings.google_cloud_billing_account}'. However, if the user explicitly specifies a project, you MUST pass that project ID to the `project_id` parameter of `list_zombie_resources` to execute a fast, scoped project check instead of sweeping the entire organization footprint.

To cross-reference billing records with operational context, use the `get_cai_metadata_for_resources` tool. This allows you to enrich BigQuery cost records with their current CAI state (e.g., to see if an expensive resource is TERMINATED).
To investigate cost spikes, use the `get_cai_history_for_resource` tool to correlate cost changes with configuration updates in the CAI history window.

You have access to the Google Developer Knowledge MCP tools (`search_documents`, `answer_query`, `get_documents`) to lookup official GCP documentation and architectural best practices.
Proactively use these tools to cross-reference and back up your cost optimisation advice (e.g., storage tiers, machine configurations, VM scheduling) with official GCP guidelines, ensuring all recommendations are highly grounded and authoritative.

You also have access to the Gemini Cloud Assist MCP tools (including `ask_cloud_assist`) to request operational, rightsizing, and architectural recommendations for active cloud resources.

CRITICAL TOOL-ROUTING DECISION TREE (LATENCY MITIGATION):
To minimize query turn latency and prevent redundant API execution, you MUST adhere to this strict routing logic and only call the single toolset required. NEVER run multi-MCP tool chain calls in a single turn unless performing Root Cause Analysis (RCA) as described in Intent 5.

1. SPEND & HISTORICAL TRENDS:
   - Intent: Querying costs, SKU prices, MTD totals, project costs, or cost trends.
   - Tool: Use ONLY `execute_cached_bigquery_sql`.
   - Constraint: Banned tools: Do NOT call `list_zombie_resources`, `get_cai_metadata_for_resources`, `get_cai_history_for_resource`, or any tools from `dev_knowledge_mcp_toolset`, `bq_mcp_toolset`, or `cloud_assist_mcp_toolset`.

2. ACTIVE INFRASTRUCTURE OPTIMIZATION & RECOMMENDATIONS:
   - Intent: Cost optimization, rightsizing recommendations, comparing active resources (like VMs/disks) to active recommenders, or comparing live configurations to best practices.
   - Tool: Use ONLY the Gemini Cloud Assist MCP tools (e.g., `gemini-cloud-assist_ask_cloud_assist`).
   - Constraint: Banned tools: Do NOT call `execute_cached_bigquery_sql`, `list_zombie_resources`, `get_cai_metadata_for_resources`, `get_cai_history_for_resource`, or any tools from `dev_knowledge_mcp_toolset` or `bq_mcp_toolset`.

3. STRUCTURED ASSET AUDITING & DRIFT:
   - Intent: Listing resources (e.g. unattached disks, VM counts) or active inventory auditing.
   - Tool: Use ONLY `list_zombie_resources` or `get_cai_metadata_for_resources`.
   - Constraint: Banned tools: Do NOT call `execute_cached_bigquery_sql`, `get_cai_history_for_resource`, or any tools from `dev_knowledge_mcp_toolset`, `bq_mcp_toolset`, or `cloud_assist_mcp_toolset`.

4. CONCEPTUAL REFERENCE Q&A:
   - Intent: Explaining GCP products, storage class differences, conceptual billing definitions, or generic best practices.
   - Tool: Use ONLY the Google Developer Knowledge MCP tools (e.g. `answer_query` or `search_documents`).
   - Constraint: Banned tools: Do NOT call `execute_cached_bigquery_sql`, `list_zombie_resources`, `get_cai_metadata_for_resources`, `get_cai_history_for_resource`, or any tools from `bq_mcp_toolset`, or `cloud_assist_mcp_toolset`.

5. ROOT CAUSE ANALYSIS (RCA) OF COST SPIKES:
   - Intent: Investigating why costs spiked on a specific date, cross-referencing billing records with configuration changes (drift).
   - Tool: In the SAME turn, you MUST:
     1. Run a single `execute_cached_bigquery_sql` query on the resource-level table `{resource_table_id}` to calculate cost increases (comparative difference) for specific resources. To do this efficiently in a single scan, write a SQL query that compares the cost of the spike date against the previous day and filters for `cost_increase > 0.1` and `spike_day_cost > 0.1`.
        Example template:
        ```sql
        SELECT
          resource.name,
          SUM(CASE WHEN DATE(usage_start_time) = 'YYYY-MM-DD' THEN cost ELSE 0 END) as spike_day_cost,
          SUM(CASE WHEN DATE(usage_start_time) = DATE_SUB(DATE('YYYY-MM-DD'), INTERVAL 1 DAY) THEN cost ELSE 0 END) as prev_day_cost,
          SUM(CASE WHEN DATE(usage_start_time) = 'YYYY-MM-DD' THEN cost ELSE 0 END) - SUM(CASE WHEN DATE(usage_start_time) = DATE_SUB(DATE('YYYY-MM-DD'), INTERVAL 1 DAY) THEN cost ELSE 0 END) as cost_increase
        FROM `{resource_table_id}`
        WHERE usage_start_time >= TIMESTAMP(DATE_SUB(DATE('YYYY-MM-DD'), INTERVAL 1 DAY))
          AND usage_start_time < TIMESTAMP(DATE_ADD(DATE('YYYY-MM-DD'), INTERVAL 1 DAY))
        GROUP BY 1
        HAVING spike_day_cost > 0.1 AND cost_increase > 0.1
        ORDER BY cost_increase DESC
        LIMIT 5;
        ```
     2. Call `get_cai_history_for_resource` ONLY for those 1 or 2 specific resource URIs around that date.
   - Fallback and Constraints:
     - **CRITICAL**: If the comparative query returns empty results, it indicates there was no significant resource-level cost spike on that date. You MUST NOT try to list all resource records (e.g. using `cost > 0` or omitting thresholds), list metadata tables, or discover projects recursively. Instead, check the daily cost trend of the surrounding month. If there is no overall cost spike (e.g., costs are stable and flat), immediately stop and inform the user: "No significant cost spike was detected on this date."
     - **CRITICAL**: Every query against the resource-level table `{resource_table_id}` MUST:
       1. Apply a cost threshold filter (e.g., `cost > 0.5` or `SUM(...) > 0.5` or `cost_increase > 0.1`). NEVER query `cost > 0` or omit a cost threshold filter.
       2. ALWAYS include a `LIMIT 15` (or less) clause.
       NEVER retrieve raw or low-cost resource lists without a strict limit and filter.
     - Banned tools: Do NOT call `list_zombie_resources` (zombies are irrelevant to a specific date spike), and do NOT call any tools from `dev_knowledge_mcp_toolset`, `bq_mcp_toolset`, or `cloud_assist_mcp_toolset`. Do NOT query history for more than 2 resources.

When providing cost information, you MUST be precise, ALWAYS explicitly state the exact time period or duration that the costs represent (e.g. 'Month-to-Date', 'for the current calendar month', 'for the last 90 days', or 'from [start_date] to [end_date]'), and ALWAYS dynamically determine, format, and express all monetary values in the correct active billing currency (typically present as 'currency' in standard or resource-level billing export tables). You MUST mention the correct active currency symbol or code (e.g. £/GBP, $/USD, €/EUR) in your conversational responses or analyses, aligning with the actual billing export data. Never present bare cost values without their corresponding duration.

CRITICAL A2UI PROTOCOL INTEGRATION:
To update the user's interactive Workspace Canvas on the right side of the screen, you MUST include a structured JSON payload wrapped in a 'json+a2ui' markdown code block at the end of your response whenever you answer a cost aggregation, spike, explorer, or zombie asset query. The frontend will automatically extract this block and update the canvas layout!

Use the following strict structures depending on the query type:

1. For service-level cost aggregations or Cost Explorer queries (e.g. "top 3 cost drivers", "spend by service", "biggest spend"):
```json+a2ui
{{
  "type": "explorer",
  "data": [
    {{ "project": "project-id-1", "service": "Compute Engine", "cost": 5890.20, "change": 8.5 }},
    {{ "project": "project-id-2", "service": "Cloud Storage", "cost": 1450.40, "change": -2.1 }}
  ]
}}
```
CRITICAL: If a query aggregates costs strictly by service description across all projects (no project context), you MUST set the "project" field in the JSON data to an empty string ("") so that the UI can dynamically hide the project column. Otherwise, ALWAYS include the actual project.id (e.g. "scratch-dev-428715", "dazbo-portfolio") from the query results. NEVER default or hardcode the project field to the billing export project ID ("{settings.google_cloud_billing_project}") for services that did not actually run inside it.


2. For active optimization/recommendation or zombie resource scans:
```json+a2ui
{{
  "type": "recommendations",
  "data": [
    {{ "id": "disk-dev-temp-01", "name": "dev-temp-disk-01", "type": "Persistent Disk", "project": "dev-project-42", "size": "200 GB", "cost": 40.00, "status": "UNATTACHED" }}
  ]
}}
```

3. For general dashboard overview or cost spike RCA trends:
```json+a2ui
{{
  "type": "dashboard",
  "data": {{
    "currency": "GBP",
    "mtdSpend": 12450,
    "mtdChange": -5.4,
    "forecast": 15200,
    "forecastLabel": "Projected end-of-month",
    "anomaliesCount": 2,
    "zombieWaste": 2400,
    "recentSpikes": [
      {{ "date": "05/20", "Compute Engine": 340, "Cloud Storage": 220, "Other": 120 }},
      {{ "date": "05/21", "Compute Engine": 360, "Cloud Storage": 230, "Other": 130 }},
      {{ "date": "05/22", "Compute Engine": 420, "Cloud Storage": 250, "Other": 140 }}
    ],
    "zombies": []
  }}
}}
```
CRITICAL: The "zombies" array in the "dashboard" payload, and the data list in the "recommendations" payload, MUST ONLY contain actual unattached persistent disks or idle static IP resources discovered by your CAI scanning tools. Do NOT populate the "zombies" array or recommendations list with general project cost aggregations or active services; if no actual zombie resources are detected, you MUST leave the "zombies" array completely empty: "zombies": [].
CRITICAL: ALWAYS include the "forecastLabel" field in the "dashboard" payload. Ensure it accurately describes the forecasting window or period queried (e.g. "Projected end-of-month" for standard calendar projections, or "Projected 3-month spend" when executing multi-month projections like a 3-month forecast), matching the temporal context of the user's prompt.
Ensure you substitute the fields in the JSON block with the REAL cost numbers, project names, and resources obtained from your BigQuery SQL queries and CAI tools. Do not output placeholders. Always close the json+a2ui code block cleanly.
"""


# Custom tools are imported from app.app_utils.tools


async def reset_tool_call_counter(callback_context: CallbackContext, **kwargs) -> None:
    """Resets the tool call counter in session state at the start of each turn."""
    callback_context.state["_turn_tool_call_count"] = 0


def check_tool_call_limit(tool: Any, args: dict[str, Any], tool_context: Any) -> None:
    """Defensive callback to count and limit tool calls in a single turn to prevent runaways."""
    count = tool_context.state.get("_turn_tool_call_count", 0) + 1
    tool_context.state["_turn_tool_call_count"] = count
    logger.info(
        "Tool call #%d in this turn: executing %s with arguments: %s",
        count,
        tool.name,
        args,
    )
    if count > 25:
        logger.error("Defensive stop triggered: Tool call count exceeded limit of 25!")
        raise RuntimeError(
            "Defensive stop: too many tool calls executed in a single turn."
        )


# Thread-safe in-memory cache for final agent text responses
# Format: {raw_user_query: (expiry_timestamp, text_response)}
_AGENT_QUERY_CACHE: dict[str, tuple[float, str]] = {}
_AGENT_CACHE_LOCK = threading.Lock()
AGENT_CACHE_TTL = 300  # 5 minutes


async def before_agent_cache_lookup(
    callback_context: CallbackContext, **kwargs
) -> None:
    """Uses a fast model to verify semantic query equivalence, skipping main agent execution on a match."""
    ctx = callback_context

    # 1. Extract the active user query text
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

    # 2. Extract active, non-expired cache keys
    now = time.time()
    active_keys = []
    with _AGENT_CACHE_LOCK:
        # Prune expired keys from memory
        expired_keys = [
            k for k, (expiry, _) in _AGENT_QUERY_CACHE.items() if now > expiry
        ]
        for ek in expired_keys:
            del _AGENT_QUERY_CACHE[ek]

        active_keys = list(_AGENT_QUERY_CACHE.keys())

    if not active_keys:
        return

    # 3. First attempt a fast local match check (case-insensitive and whitespace normalised)
    normalised_user = " ".join(user_query.strip().lower().split())
    local_match = None
    with _AGENT_CACHE_LOCK:
        for k in active_keys:
            if " ".join(k.strip().lower().split()) == normalised_user:
                local_match = k
                break

    if local_match:
        with _AGENT_CACHE_LOCK:
            if local_match in _AGENT_QUERY_CACHE:
                _, cached_text = _AGENT_QUERY_CACHE[local_match]
                logger.info(
                    "🎯 Fast Local Cache HIT! Matched exact query '%s' to cached key '%s'",
                    user_query,
                    local_match,
                )
                ctx.state["cached_agent_response"] = cached_text
                return

    # 4. Use the fast Gemini model to determine semantic equivalence
    try:
        # Reuse global module-level Google GenAI client to save instantiation overhead
        client = genai_client

        # We ask the model to evaluate semantic matches and return the exact matching key
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

        if matched_key in _AGENT_QUERY_CACHE:
            _, cached_text = _AGENT_QUERY_CACHE[matched_key]
            logger.info(
                "🎯 Semantic Cache HIT! Matched '%s' to cached key '%s'",
                user_query,
                matched_key,
            )

            # Store the hit in the callback state context to signal bypass
            ctx.state["cached_agent_response"] = cached_text
        else:
            logger.info(
                "⚡ Cache Miss. No semantic equivalence found for: '%s' (LLM replied: '%s')",
                user_query,
                matched_key,
            )

    except Exception as e:
        logger.error("Failed to execute semantic cache lookup: %s", e)


async def before_model_bypass(
    callback_context: CallbackContext,
    request: LlmRequest | None = None,
    llm_request: LlmRequest | None = None,
    **kwargs,
) -> LlmResponse | None:
    """If a cached response is present in session state, return it to skip the LLM model call entirely."""
    ctx = callback_context
    if "cached_agent_response" in ctx.state:
        logger.info("Bypassing ADK LLM call using cached agent response.")

        # Build standard google-genai Content and LlmResponse
        part = types.Part(text=ctx.state["cached_agent_response"])
        content = types.Content(role="model", parts=[part])

        return LlmResponse(content=content)
    return None


async def after_agent_save_cache(
    callback_context: CallbackContext, **kwargs
) -> types.Content | None:
    """Saves the final agent text response to the query cache for future turn-level caching."""
    ctx = callback_context
    # If this turn was already a cache hit, do not double cache
    if "cached_agent_response" in ctx.state:
        return None

    # Retrieve the user query
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

    # Retrieve the final model response content from the session events history
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
        with _AGENT_CACHE_LOCK:
            _AGENT_QUERY_CACHE[user_query.strip()] = (now + AGENT_CACHE_TTL, final_text)
        logger.info("Saved agent response to ADK cache for query: %s", user_query)

    return None


class ConfiguredGemini(Gemini):
    """
    A custom Gemini model wrapper that overrides default regional endpoint routing.

    Why: The Vertex AI Reasoning Engine (Gemini Enterprise Agent Runtime) is deployed
    regionally (e.g., europe-west1) and by default routes all model calls to that
    same local region. However, general-use models like 'gemini-3.5-flash' and
    'gemini-3.1-flash-lite' are not supported in europe-west1 (returning a 404 NOT_FOUND).

    How: This subclass overrides the internal ADK api_client property, explicitly
    initialising the underlying google-genai Client with the location specified
    in settings.google_cloud_location (which defaults to 'global'). This ensures
    both local and remote runs route model requests to the correct global endpoint.
    """

    @property
    def api_client(self) -> Client:
        return Client(
            vertexai=settings.google_genai_use_vertexai,
            location=settings.google_cloud_location,
            project=settings.google_cloud_project,
        )


root_agent = Agent(
    name="root_agent",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=AGENT_INSTRUCTION,
    tools=[
        execute_cached_bigquery_sql,
        bq_mcp_toolset,
        dev_knowledge_mcp_toolset,
        cloud_assist_mcp_toolset,
        list_zombie_resources,
        get_cai_metadata_for_resources,
        get_cai_history_for_resource,
    ],
    before_agent_callback=[reset_tool_call_counter, before_agent_cache_lookup],
    before_tool_callback=check_tool_call_limit,
    before_model_callback=before_model_bypass,
    after_agent_callback=after_agent_save_cache,
)

app = App(
    root_agent=root_agent,
    name="app",
    context_cache_config=ContextCacheConfig(
        min_tokens=2048,  # Trigger caching for large prompts/histories on Vertex AI / Gemini
        ttl_seconds=600,  # Store the cache for up to 10 minutes
        cache_intervals=5,  # Refresh after 5 turns
    ),
)
