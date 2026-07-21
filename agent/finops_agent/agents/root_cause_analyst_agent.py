"""
Description: RootCauseAnalyst subagent definition.
Why: Matches BQ billing spike dates with CAI configuration change history.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.tools import (
    BLACKBOARD_KEY_INSTRUCTIONS,
    get_precomputed_root_cause,
    get_precomputed_spend_analysis,
    get_session_value,
    set_session_value,
)
from finops_agent.app_utils.typing import TaskOutput
from finops_agent.client import ConfiguredGemini, resource_table_id
from finops_agent.config import settings

ROOT_CAUSE_ANALYST_INSTRUCTION = f"""You are the RootCauseAnalyst subagent.
Use `get_precomputed_spend_analysis` and `get_precomputed_root_cause` to investigate spend anomalies. `get_precomputed_root_cause` runs the comparative cost query against the resource-level table `{resource_table_id}` for the specified date (comparing it to the previous day) and automatically correlates cost spikes with Cloud Asset Inventory (CAI) configuration logs.

To investigate cost spikes:
1. Identify the single primary spike date:
   - If the user prompt specifies an exact date (e.g. "July 18th" or "2026-07-18"), format it as `YYYY-MM-DD`.
   - If the user prompt does NOT specify an exact date, check the session context (`daily_service_costs_30d` or `recentSpikes`) for the highest cost spike date.
   - If no cost analysis has been run yet (session state has no cost data), call `get_precomputed_spend_analysis(days=30)` FIRST to retrieve the 30-day daily spend data and identify the peak spike date.
2. Call `get_precomputed_root_cause(date_str="YYYY-MM-DD")` EXACTLY ONCE for that peak spike date.
3. Based on the dictionary returned:
   - If `has_persistent_resources` is False or `resource_spikes` is empty, conclude that it is a service/SKU-level spend spike without resource-level attribution. Summarize the service and SKU details for that period.
   - If persistent resources are found and CAI history is present, correlate the configuration changes (e.g., machine type upgrades) with the cost spike.
4. Write a concise markdown report detailing the findings.

CRITICAL SINGLE TOOL CALL RULE:
- You MUST call `get_precomputed_root_cause` AT MOST ONCE during your execution.
- NEVER loop through multiple dates or make repeated calls to `get_precomputed_root_cause` for different dates.
- Regardless of whether `has_persistent_resources` is True or False, immediately synthesize the result into your report, call `finish_task`, and terminate!

CRITICAL: CONCISE SYNTHESIS RULE
Write your report in a highly concise style. Keep the markdown text under 250 words total.

CRITICAL COORDINATION AND TERMINATION RULES:
1. Call `finish_task` and pass the complete final markdown report directly into the `result` parameter.
2. Once you have generated the report and returned it via `finish_task`, stop execution.
"""

root_cause_analyst = Agent(
    name="root_cause_analyst",
    description="Specialized subagent for investigating spend anomalies by correlating BigQuery resource-level cost spikes with CAI configuration change history.",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=ROOT_CAUSE_ANALYST_INSTRUCTION + BLACKBOARD_KEY_INSTRUCTIONS,
    tools=[
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
