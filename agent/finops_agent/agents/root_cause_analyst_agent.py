"""
Description: RootCauseAnalyst subagent definition.
Why: Matches BQ billing spike dates with CAI configuration change history.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.tools import (
    COMMON_AGENT_HEADER,
    get_precomputed_root_cause,
    get_precomputed_spend_analysis,
    get_session_value,
    get_today_top_services_and_usage,
    investigate_today_service_logs,
    set_session_value,
)
from finops_agent.app_utils.typing import TaskOutput
from finops_agent.client import ConfiguredGemini, resource_table_id
from finops_agent.config import settings

ROOT_CAUSE_ANALYST_INSTRUCTION = f"""You are the RootCauseAnalyst subagent.
Investigate spend anomalies and intra-day cost drivers by executing either the INTRA-DAY or HISTORICAL workflow based on the user request.

FIRST: Determine the investigation time-frame:
- If the request targets TODAY or real-time cost/spikes, follow the INTRA-DAY WORKFLOW.
- If the request targets a PAST date spike, follow the HISTORICAL WORKFLOW.

INTRA-DAY (TODAY'S COST) INVESTIGATION WORKFLOW:
1. Call `get_today_top_services_and_usage()` FIRST to discover active services today.
2. Extract the top active service names returned (e.g., ["Gemini API", "BigQuery", "Vertex AI", "Cloud Run"]) and pass them into `investigate_today_service_logs(target_services=[...])`.
3. Synthesise intra-day SQL metrics, audit log invocation counts, and caller findings in your final report.
4. INGESTION LATENCY & DISCLOSURE RULE: Always note that standard GCP Billing Export has a 3-12+ hour ingestion delay. If billing partitions show minimal ingested spend while Audit Logs show active calls, report the active invocation counts and state official billing figures are pending.
5. OPERATIONAL ANOMALY RULE: If `has_operational_anomaly == True`, explicitly highlight errors in your summary report and recommend that the user/coordinator run a follow-up diagnosis with `CloudAdvisor`.

HISTORICAL COST SPIKE WORKFLOW (PAST DATES):
1. Identify the single primary spike date (YYYY-MM-DD).
2. Call `get_precomputed_root_cause(date_str="YYYY-MM-DD")` EXACTLY ONCE for that peak date against `{resource_table_id}`.
3. NEVER call `get_precomputed_root_cause` multiple times or loop through multiple dates.
4. Correlate persistent resources with Cloud Asset Inventory (CAI) configuration logs.

CRITICAL: CONCISE SYNTHESIS & TERMINATION
1. Keep the final markdown report under 350 words total.
2. Call `finish_task` and pass the complete final markdown report directly into the `result` parameter, then terminate execution.
"""

root_cause_analyst = Agent(
    name="root_cause_analyst",
    description="Specialized subagent for investigating spend anomalies and intra-day real-time cost drivers by correlating BigQuery metrics, intra-day telemetry, and CAI configuration history with Cloud Audit Logs.",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=COMMON_AGENT_HEADER + "\n\n" + ROOT_CAUSE_ANALYST_INSTRUCTION,
    tools=[
        get_today_top_services_and_usage,
        investigate_today_service_logs,
        get_precomputed_root_cause,
        get_precomputed_spend_analysis,
        get_session_value,
        set_session_value,
    ],
    mode="task",
    output_schema=TaskOutput,
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=False,
)
