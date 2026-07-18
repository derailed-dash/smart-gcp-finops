"""
Description: RootCauseAnalyst subagent definition.
Why: Matches BQ billing spike dates with CAI configuration change history.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.cai_tools import get_cai_history_for_resource
from finops_agent.app_utils.tools import execute_cached_bigquery_sql
from finops_agent.client import ConfiguredGemini, resource_table_id
from finops_agent.config import settings

ROOT_CAUSE_ANALYST_INSTRUCTION = f"""You are the RootCauseAnalyst subagent.
Use BQ billing tools and CAI tools to match date ranges of cost spikes with CAI configuration change history to diagnose the root cause of unexpected spend.

To investigate cost spikes, you MUST:
1. Run a single `execute_cached_bigquery_sql` query on the resource-level table `{resource_table_id}` to calculate cost increases (comparative difference) for specific resources. Compare the cost of the spike date against the previous day and filter for `cost_increase > 0.1` and `spike_day_cost > 0.1`.
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

If the comparative query returns empty results, indicate that no significant resource-level cost spike was detected on that date.
"""

root_cause_analyst = Agent(
    name="root_cause_analyst",
    description="Specialized subagent for investigating spend anomalies by correlating BigQuery resource-level cost spikes with CAI configuration change history.",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=ROOT_CAUSE_ANALYST_INSTRUCTION,
    tools=[
        execute_cached_bigquery_sql,
        get_cai_history_for_resource,
    ],
    mode="task",
)
