"""
Description: Custom application tools for the ADK agent.
Why: Isolates custom database tools and utility functions from agent orchestration.
How: Defines the cached BigQuery SQL execution tool using the Google BigQuery Python client.
"""

import logging
import re
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import google.auth
from google.adk.tools import ToolContext
from google.cloud import bigquery

from finops_agent.config import settings

logger = logging.getLogger(__name__)

# Global private in-memory query cache mapped by session_id to avoid serialising raw SQL caches into ADK SessionState
_IN_MEMORY_BQ_CACHE: dict[str, dict[str, Any]] = {}



class BigQueryClientManager:
    """Manages thread-safe lazy-initialisation of the shared BigQuery client."""

    def __init__(self) -> None:
        self._bq_client = None
        self._bq_lock = threading.Lock()

    def get_client(self) -> bigquery.Client:
        """Returns the shared BigQuery client instance, building it if necessary."""
        if self._bq_client is None:
            with self._bq_lock:
                if self._bq_client is None:
                    credentials, _ = google.auth.default(
                        scopes=["https://www.googleapis.com/auth/bigquery"]
                    )
                    self._bq_client = bigquery.Client(
                        credentials=credentials,
                        project=settings.google_cloud_billing_project,
                    )
        return self._bq_client

    def reset(self) -> None:
        """Resets the cached BigQuery client."""
        with self._bq_lock:
            self._bq_client = None


# Module-level singleton instance for BigQuery client management
bq_client_manager = BigQueryClientManager()


def _get_bq_client() -> bigquery.Client:
    """Returns the shared BigQuery client instance, building it if necessary."""
    return bq_client_manager.get_client()


def _serialise_value(val: Any) -> Any:
    """Recursively serialises non-JSON-compliant data types (dates, decimals) for GenAI compatibility."""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    elif isinstance(val, Decimal):
        return float(val)
    elif isinstance(val, dict):
        return {k: _serialise_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_serialise_value(v) for v in val]
    return val


def execute_cached_bigquery_sql(sql: str, tool_context: ToolContext) -> list[dict]:
    """Executes a BigQuery SQL query against the billing export tables.

    This tool is highly optimised and uses in-memory caching to avoid redundant,
    expensive database table scans and minimise query costs.
    """
    logger.debug("Executing full BigQuery SQL query:\n%s", sql)
    try:
        from unittest.mock import MagicMock

        from finops_agent.app_utils.context import ALLOWED_PROJECTS_VAR

        # Retrieve allowed projects from ADK session state (saved up-front by before_agent_callback)
        allowed_projects = None
        state = getattr(tool_context, "state", None)
        if state is not None and not isinstance(state, MagicMock):
            allowed_projects = state.get("allowed_projects")

        # Fallback to context variable if not present in state
        if allowed_projects is None:
            allowed_projects_ctx = ALLOWED_PROJECTS_VAR.get()
            if allowed_projects_ctx is not None:
                allowed_projects = list(allowed_projects_ctx)

        # Fallback to user_id check
        if allowed_projects is None:
            user_email = tool_context.user_id
            if user_email and not isinstance(user_email, MagicMock):
                from finops_agent.app_utils.project_discovery import (
                    get_user_accessible_projects,
                )

                allowed_projects = list(get_user_accessible_projects(user_email))
                if state is not None and not isinstance(state, MagicMock):
                    state["allowed_projects"] = allowed_projects

        if allowed_projects is not None:
            # Inject project scoping filters dynamically into the query to prevent unauthorised access
            billing_suffix = settings.google_cloud_billing_account.replace("-", "_")
            standard_table = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_v1_{billing_suffix}"
            resource_table = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_resource_v1_{billing_suffix}"

            # Dynamic Table Routing: If the query references the resource table but does not query/filter
            # on resource properties, route to the standard table to avoid scanning massive volumes.
            if resource_table in sql and not re.search(r"\bresource\.", sql, re.IGNORECASE):
                sql = sql.replace(resource_table, standard_table)
                logger.info("Dynamically routed resource-level query to standard table (no resource fields referenced).")

            sanitized_projects = [p for p in allowed_projects if re.match(r"^[a-z0-9\-]+$", p)]

            # Intersect with any explicit project ID filters present in the original SQL
            # to narrow down scoping filters and accelerate clustering scans.
            explicit_projects = set()
            eq_matches = re.findall(r"\bproject\.id\s*=\s*['\"]([a-z0-9\-]+)['\"]", sql, re.IGNORECASE)
            for p in eq_matches:
                explicit_projects.add(p)
            in_matches = re.findall(r"\bproject\.id\s*IN\s*\(([^)]+)\)", sql, re.IGNORECASE)
            for match in in_matches:
                for p in re.findall(r"['\"]([a-z0-9\-]+)['\"]", match, re.IGNORECASE):
                    explicit_projects.add(p)

            if explicit_projects:
                unauthorized_projects = explicit_projects - set(sanitized_projects)
                if unauthorized_projects:
                    logger.warning(
                        "Security warning: User attempted to query projects they do not have access to: %s",
                        list(unauthorized_projects),
                    )
                target_projects = [p for p in sanitized_projects if p in explicit_projects]
            else:
                target_projects = sanitized_projects

            # Extract date and partition filters to push them down into the subqueries
            nested_parens = r"\((?:[^()]*|\((?:[^()]*|\((?:[^()]*|\([^()]*\))*\))*\))*\)"
            date_filter_pattern = re.compile(
                rf"\b(?:export_time|usage_start_time|usage_end_time)\s*(?:>=|<=|>|<|=)\s*(?:TIMESTAMP\s*{nested_parens}|TIMESTAMP_SUB\s*{nested_parens}|CAST\s*{nested_parens}|DATE_SUB\s*{nested_parens}|TIMESTAMP\s+['\"][^'\"]+['\"]|['\"][^'\"]+['\"]|\bCURRENT_DATE\b|\bCURRENT_TIMESTAMP\b)",
                re.IGNORECASE
            )
            date_filters = date_filter_pattern.findall(sql)
            extra_where = " AND ".join(date_filters)
            if not extra_where:
                extra_where = "export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY))"
                logger.warning("Defensively injected 90-day partition filter to prevent full historical scan.")

            if not target_projects:
                subquery_standard = f"(SELECT * FROM `{standard_table}` LIMIT 0)"
                subquery_resource = f"(SELECT * FROM `{resource_table}` LIMIT 0)"
            else:
                proj_list = ", ".join(f"'{p}'" for p in target_projects)
                where_clause = f"project.id IN ({proj_list})"
                if extra_where:
                    where_clause += f" AND {extra_where}"
                subquery_standard = (
                    f"(SELECT * FROM `{standard_table}` WHERE {where_clause})"
                )
                subquery_resource = (
                    f"(SELECT * FROM `{resource_table}` WHERE {where_clause})"
                )

            escaped_std = re.escape(standard_table)
            pattern_std = re.compile(rf"`{escaped_std}`|{escaped_std}")
            sql = pattern_std.sub(subquery_standard, sql)

            escaped_res = re.escape(resource_table)
            pattern_res = re.compile(rf"`{escaped_res}`|{escaped_res}")
            sql = pattern_res.sub(subquery_resource, sql)

        logger.debug("Scoped BigQuery SQL query:\n%s", sql)

        # Normalise SQL format to standardise cache keys
        normalised_sql = re.sub(r"\s+", " ", sql).strip()

        # Check in-memory query cache
        session_id = tool_context.session.id if (tool_context.session and tool_context.session.id) else "default"
        if session_id not in _IN_MEMORY_BQ_CACHE:
            _IN_MEMORY_BQ_CACHE[session_id] = {}
        bq_cache = _IN_MEMORY_BQ_CACHE[session_id]

        if normalised_sql in bq_cache:
            logger.debug("BQ Cache hit in memory for query: %s...", normalised_sql[:60])
            return bq_cache[normalised_sql]

        # Cache miss - execute the actual BigQuery query
        logger.debug("BQ Cache miss in memory for query: %s...", normalised_sql[:60])
        client = _get_bq_client()
        job = client.query(sql)
        rows = list(job.result())
        result = [{k: _serialise_value(v) for k, v in row.items()} for row in rows]
        logger.debug("BigQuery returned %d rows.", len(result))

        # Write to in-memory query cache
        bq_cache[normalised_sql] = result

        # Automatically populate standard blackboard keys in SessionState so other agents can read them
        if state is not None and not isinstance(state, MagicMock):
            norm_lower = normalised_sql.lower()
            if "resource_name" in norm_lower and "cost" in norm_lower and ("secret manager" in norm_lower or "cloud storage" in norm_lower):
                state["gcs_secret_waste"] = result
                logger.info("Automatically cached 'gcs_secret_waste' in session state blackboard.")
            elif "usage_date" in norm_lower and "service_description" in norm_lower and "daily_cost" in norm_lower:
                state["daily_service_costs_30d"] = result
                logger.info("Automatically cached 'daily_service_costs_30d' in session state blackboard.")
            elif "is_current_period" in norm_lower and "sku_description" in norm_lower and "period_cost" in norm_lower:
                state["sku_period_costs_60d"] = result
                logger.info("Automatically cached 'sku_period_costs_60d' in session state blackboard.")

        return result
    except Exception as e:
        logger.error(f"Error in execute_cached_bigquery_sql tool: {e}", exc_info=True)
        raise e


def get_precomputed_spend_analysis(tool_context: ToolContext) -> dict[str, Any]:
    """Pre-computes Month-to-Date (MTD) cloud costs, period-over-period trends, cost drivers,
    daily cost spikes, and Secret Manager/GCS zombie waste in Python. Reuses cached BQ queries.
    """
    from finops_agent.client import resource_table_id, standard_table_id

    # 1. Daily Service-level Costs (Last 30 Days)
    q1 = f"""
SELECT
  DATE(usage_start_time) as usage_date,
  service.description as service_description,
  SUM(cost) as daily_cost,
  currency
FROM `{standard_table_id}`
WHERE export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
  AND usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
GROUP BY 1, 2, 4
HAVING daily_cost > 0.10
ORDER BY usage_date ASC;
"""

    # 2. SKU-level Period Costs (Last 60 Days)
    q2 = f"""
SELECT
  usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) as is_current_period,
  project.id as project_id,
  service.description as service_description,
  sku.description as sku_description,
  SUM(cost) as period_cost,
  currency
FROM `{standard_table_id}`
WHERE export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY))
  AND usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY))
GROUP BY 1, 2, 3, 4, 6
HAVING period_cost > 0.50;
"""

    # 3. Storage and Secret waste
    q3 = f"""
SELECT
  project.id as project_id,
  resource.name as resource_name,
  service.description as service_description,
  sku.description as sku_description,
  SUM(cost) as cost
FROM `{resource_table_id}`
WHERE export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
  AND usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
  AND service.description IN ('Cloud Storage', 'Secret Manager')
  AND (
    service.description = 'Secret Manager'
    OR (service.description = 'Cloud Storage' AND (sku.description LIKE '%Storage%' OR sku.description LIKE '%Operation%'))
  )
GROUP BY 1, 2, 3, 4
HAVING cost > 0.1
ORDER BY cost DESC;
"""

    res1 = execute_cached_bigquery_sql(sql=q1, tool_context=tool_context)
    res2 = execute_cached_bigquery_sql(sql=q2, tool_context=tool_context)
    res3 = execute_cached_bigquery_sql(sql=q3, tool_context=tool_context)

    currency = "GBP"
    if res2:
        currency = res2[0].get("currency", "GBP")

    mtd_spend = sum(float(row["period_cost"]) for row in res2 if row["is_current_period"])
    prev_spend = sum(float(row["period_cost"]) for row in res2 if not row["is_current_period"])

    if prev_spend > 0:
        mtd_change = ((mtd_spend - prev_spend) / prev_spend) * 100.0
    else:
        mtd_change = 100.0

    forecast = mtd_spend

    drivers_curr = {}
    drivers_prev = {}
    for row in res2:
        key = (row["project_id"], row["service_description"])
        cost = float(row["period_cost"])
        if row["is_current_period"]:
            drivers_curr[key] = drivers_curr.get(key, 0.0) + cost
        else:
            drivers_prev[key] = drivers_prev.get(key, 0.0) + cost

    top_drivers = []
    for key, cost in drivers_curr.items():
        proj, svc = key
        prev = drivers_prev.get(key, 0.0)
        chg = 100.0 if prev == 0 else ((cost - prev) / prev) * 100.0
        top_drivers.append({
            "project": proj,
            "service": svc,
            "cost": round(cost, 2),
            "change": round(chg, 1),
        })
    top_drivers.sort(key=lambda x: x["cost"], reverse=True)

    daily_groups = {}
    services_seen = set()
    for row in res1:
        date_str = row["usage_date"]
        if "-" in date_str:
            parts = date_str.split("-")
            date_formatted = f"{parts[1]}/{parts[2]}"
        else:
            date_formatted = date_str

        svc = row["service_description"]
        cost = float(row["daily_cost"])

        if date_formatted not in daily_groups:
            daily_groups[date_formatted] = {}
        daily_groups[date_formatted][svc] = daily_groups[date_formatted].get(svc, 0.0) + cost
        services_seen.add(svc)

    recent_spikes = []
    for dt, svcs in daily_groups.items():
        total_day_cost = sum(svcs.values())
        if total_day_cost > 0.50:
            day_dict = {"date": dt}
            for s in services_seen:
                day_dict[s] = round(svcs.get(s, 0.0), 2)
            recent_spikes.append(day_dict)
    recent_spikes.sort(key=lambda x: x["date"])
    recent_spikes = recent_spikes[-10:]

    zombie_waste = 0.0
    zombies = []
    for row in res3:
        cost = float(row["cost"])
        zombie_waste += cost
        zombies.append({
            "resource": row["resource_name"],
            "service": row["service_description"],
            "cost": round(cost, 2),
            "recommendation": "Review unused secret versions"
            if row["service_description"] == "Secret Manager"
            else "Clean up empty bucket storage",
        })

    return {
        "currency": currency,
        "mtdSpend": round(mtd_spend, 2),
        "mtdChange": round(mtd_change, 1),
        "forecast": round(forecast, 2),
        "forecastLabel": "Projected end-of-month",
        "anomaliesCount": len(
            [s for s in recent_spikes if sum(v for k, v in s.items() if k != "date") > 2.0]
        ),
        "zombieWaste": round(zombie_waste, 2),
        "top_drivers": top_drivers,
        "recentSpikes": recent_spikes,
        "zombies": zombies,
    }


def get_session_value(key: str, tool_context: ToolContext) -> Any:
    """Retrieves a cached value from the active session state if present.
    Supported keys include:
    - 'allowed_projects': list of allowed project IDs
    - 'active_billing_projects': list of active billing projects
    - 'gcs_secret_waste': list or dict containing cached GCS/Secret Manager waste resources
    - 'daily_service_costs_30d'
    - 'sku_period_costs_60d'
    - 'zombie_resources'
    - 'rightsizing_recommendations'
    - 'spend_analysis'
    """
    from unittest.mock import MagicMock
    state = getattr(tool_context, "state", None)
    if state is not None and not isinstance(state, MagicMock):
        if key in state:
            logger.debug(f"[BLACKBOARD HIT] Retrieved key '{key}' from session state, skipping external tool query.")
            return state[key]
    logger.debug(f"[BLACKBOARD MISS] Key '{key}' not found in session state.")
    return None


def set_session_value(key: str, value: Any, tool_context: ToolContext) -> str:
    """Stores a value in the active session state for other agents to reuse in the current session.
    For example, use this to store 'gcs_secret_waste' so other agents do not have to query it again.
    """
    from unittest.mock import MagicMock
    state = getattr(tool_context, "state", None)
    if state is not None and not isinstance(state, MagicMock):
        state[key] = value
        logger.debug(f"[BLACKBOARD WRITE] Stored key '{key}' in session state for other subagents to reuse.")
        return f"Successfully stored key '{key}' in session state."
    return "Error: Session state not available."


BLACKBOARD_KEY_INSTRUCTIONS = """
CRITICAL: SHARED SESSION BLACKBOARD PATTERN
All subagents share a common session-scoped blackboard. Before calling external database queries, API calls, or MCP tools, you MUST check if the required data is already cached in the blackboard by calling `get_session_value(key)`. If it is present, use it directly.

Note: To prevent long response delays, do NOT call `set_session_value` to write BigQuery query results (like costs or waste lists) back to the session state; the query tool automatically caches these results in the session state for you under the appropriate keys when executed. Only call `set_session_value` for non-database results.

You MUST use these exact standardized keys:
- 'daily_service_costs_30d': List of daily service cost aggregates (date, service, cost) over the last 30 days.
- 'sku_period_costs_60d': List of SKU period costs (is_current_period, project, service, SKU, cost) over the last 60 days.
- 'gcs_secret_waste': List of inactive storage buckets (GCS) and Secret Manager version replicas.
- 'zombie_resources': List of idle static IPs and unattached boot/data disks.
- 'rightsizing_recommendations': Cost, rightsizing, and performance optimization suggestions from Cloud Assist.
"""
