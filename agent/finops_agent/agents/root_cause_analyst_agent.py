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
Use `get_precomputed_spend_analysis`, `get_precomputed_root_cause`, `get_today_top_services_and_usage`, and `investigate_today_service_logs` to investigate spend anomalies and intra-day cost drivers. `get_precomputed_root_cause` runs the comparative cost query against the resource-level table `{resource_table_id}` for historical dates (comparing to previous day) and correlates spikes with Cloud Asset Inventory (CAI) configuration logs.

CRITICAL INTRA-DAY (TODAY'S COST) INVESTIGATION WORKFLOW:
1. Call `get_today_top_services_and_usage()` FIRST to discover which services are active and driving usage today (combining BigQuery INFORMATION_SCHEMA, real-time Cloud Audit Logs, and billing export partitions).
2. Extract the top active service names returned (e.g., ["Gemini API", "BigQuery", "Vertex AI", "Cloud Run"]) and pass them directly into `investigate_today_service_logs(target_services=[...])`.
3. Synthesise both intra-day SQL/metric figures, real-time audit log API invocation counts, and Cloud Audit Log caller findings in your final report.
4. INGESTION LATENCY & DISCLOSURE RULE: Always explicitly note that standard GCP Billing Export has a 3-12+ hour ingestion delay. If billing export partitions show minimal ingested spend (e.g. £0.04) while real-time Cloud Audit Logs show active API invocations (e.g. Gemini API / Vertex AI / BigQuery calls), explicitly report the active API invocation counts from Cloud Audit Logs and state that official billing export figures are pending ingestion.
5. OPERATIONAL ANOMALY RULE: If `investigate_today_service_logs` detects operational errors (`has_operational_anomaly == True`), explicitly highlight the errors/anomalies in your executive summary and offer/recommend delegating to `CloudAdvisor` (or invoking Gemini Cloud Assist `investigate_issue`) to perform infrastructure root-cause diagnostics.

To investigate historical cost spikes (past dates):
1. Identify the single primary spike date (formatted as YYYY-MM-DD).
2. Call `get_precomputed_root_cause(date_str="YYYY-MM-DD")` EXACTLY ONCE for that peak spike date.
3. Correlate persistent resources with CAI configuration logs.
4. Write a concise markdown report detailing the findings.

CRITICAL SINGLE TOOL CALL RULE:
- You MUST call `get_precomputed_root_cause` AT MOST ONCE during your execution.
- NEVER loop through multiple dates or make repeated calls to `get_precomputed_root_cause` for different dates.
- Immediately synthesize the result into your report, call `finish_task`, and terminate!

CRITICAL: CONCISE SYNTHESIS RULE
Write your report in a highly concise style. Keep the markdown text under 250 words total.

CRITICAL COORDINATION AND TERMINATION RULES:
1. Call `finish_task` and pass the complete final markdown report directly into the `result` parameter.
2. Once you have generated the report and returned it via `finish_task`, stop execution.
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
