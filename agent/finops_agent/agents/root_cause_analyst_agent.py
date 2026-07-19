"""
Description: RootCauseAnalyst subagent definition.
Why: Matches BQ billing spike dates with CAI configuration change history.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.tools import (
    BLACKBOARD_KEY_INSTRUCTIONS,
    get_precomputed_root_cause,
    get_session_value,
    set_session_value,
)
from finops_agent.client import ConfiguredGemini, resource_table_id
from finops_agent.config import settings

ROOT_CAUSE_ANALYST_INSTRUCTION = f"""You are the RootCauseAnalyst subagent.
Use the `get_precomputed_root_cause` tool to investigate spend anomalies. It runs the comparative cost query against the resource-level table `{resource_table_id}` for the specified date (comparing it to the previous day) and automatically correlates cost spikes with Cloud Asset Inventory (CAI) configuration logs.

To investigate cost spikes:
1. Call `get_precomputed_root_cause(date_str="YYYY-MM-DD")` for the specific date of the spike (e.g. "2026-07-18").
2. Based on the dictionary returned:
   - If `has_persistent_resources` is False (or resource spikes list is empty/has null names), conclude that it is a service/SKU-level spend spike (without resource-level attribution). Summarize the service and SKU details.
   - If persistent resources are found and CAI history is present, correlate the configuration changes (e.g., machine type upgrades) with the cost spike.
3. Write a concise markdown report detailing the findings.

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
        get_session_value,
        set_session_value,
    ],
    mode="task",
)
