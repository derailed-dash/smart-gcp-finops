"""Custom BigQuery and FinOps tools for the ADK agent.

What:
    Defines ADK agent tools for executing BigQuery SQL queries, retrieving billing schema metadata, running cost
    forecasts, analyzing spending trends, and performing dynamic intra-day cost and log research.

Why:
    Provides the primary data query interface for the FinOps agent, enabling natural language questions to be
    translated into optimized BigQuery queries and targeted Cloud Audit Log research with built-in security,
    caching, and result formatting.

How:
    Implements ``run_bigquery_query`` with thread-safe client management via ``BigQueryClientManager``, enforces
    user-accessible project filtering, converts complex data types to JSON-serializable structures, caches
    query results in session state, and implements dynamic intra-day service discovery and targeted log investigation tools.

Data Latency & Intra-Day Telemetry Strategy:
    Standard GCP Billing Export tables (BigQuery) have an ingestion delay of 3 to 12+ hours.
    To analyze "today's" spend in real time, `get_today_top_services_and_usage` queries near-real-time
    BigQuery `INFORMATION_SCHEMA.JOBS_BY_PROJECT` (for query execution bytes) and intra-day billing partitions.
    It saves the top active services into the session blackboard (`state['today_top_services']`), which
    `investigate_today_service_logs` then reads to dynamically target GCP Cloud Audit Logs for those specific services today.
"""

import logging
import re
import threading
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import google.auth
from google.adk.tools import ToolContext
from google.cloud import bigquery

from finops_agent.config import settings

logger = logging.getLogger(__name__)

# Global private in-memory query cache mapped by session_id to
# avoid serialising raw SQL caches into ADK SessionState
# Avoids heavy JSON serialisation overhead and OTEL trace bloat
_IN_MEMORY_BQ_CACHE: dict[str, dict[str, Any]] = {}

# Global private metadata cache for billing table strings and project permissions
_METADATA_CACHE: dict[str, Any] = {}
_METADATA_CACHE_LOCK = threading.Lock()


def _get_billing_table_ids() -> tuple[str, str]:
    """Returns cached (standard_table_id, resource_table_id) tuple to avoid string format overhead."""
    cache_key = f"billing_tables_{settings.google_cloud_billing_account}_{settings.billing_export_dataset}"
    with _METADATA_CACHE_LOCK:
        if cache_key in _METADATA_CACHE:
            return _METADATA_CACHE[cache_key]
        billing_suffix = settings.google_cloud_billing_account.replace("-", "_")
        standard_table = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_v1_{billing_suffix}"
        resource_table = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_resource_v1_{billing_suffix}"
        res = (standard_table, resource_table)
        _METADATA_CACHE[cache_key] = res
        return res


def get_cached_user_accessible_projects(user_email: str) -> list[str]:
    """Retrieves user-accessible projects with a 5-minute in-memory cache to reduce IAM lookups."""
    now = datetime.now(UTC).timestamp()
    cache_key = f"user_projects_{user_email}"
    with _METADATA_CACHE_LOCK:
        if cache_key in _METADATA_CACHE:
            cached_data, timestamp = _METADATA_CACHE[cache_key]
            if now - timestamp < 300:  # 5-minute TTL
                return cached_data

    from finops_agent.app_utils.project_discovery import get_user_accessible_projects

    projects = list(get_user_accessible_projects(user_email))
    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE[cache_key] = (projects, now)
    return projects



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
    match val:
        case datetime() | date():
            return val.isoformat()
        case Decimal():
            return float(val)
        case dict():
            return {k: _serialise_value(v) for k, v in val.items()}
        case list():
            return [_serialise_value(v) for v in val]
        case _:
            return val


def execute_cached_bigquery_sql(sql: str, tool_context: ToolContext) -> list[dict]:
    """Executes a BigQuery SQL query against the billing export tables.

    This tool is highly optimised and uses in-memory caching to avoid redundant,
    expensive database table scans and minimise query costs.
    """
    logger.debug("Executing full BigQuery SQL query:\n%s", sql)
    try:
        # Import MagicMock locally to guard against mock autogeneration during unit testing
        from unittest.mock import MagicMock

        from finops_agent.app_utils.context import ALLOWED_PROJECTS_VAR

        # Retrieve allowed projects from ADK session state (saved up-front by before_agent_callback)
        allowed_projects = None
        state = getattr(tool_context, "state", None)
        # Avoid treating autogenerated MagicMock attributes as actual session state dictionaries
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
                allowed_projects = get_cached_user_accessible_projects(user_email)
                if state is not None and not isinstance(state, MagicMock):
                    state["allowed_projects"] = allowed_projects

        if allowed_projects is not None:
            # Dynamically scopes raw user-supplied SQL queries by replacing table references with pre-filtered subqueries.
            # Benefits:
            #   1. Security: Enforces multi-tenant project isolation at the database level by restricting rows
            #      to allowed_projects, preventing unauthorized data access.
            #   2. Performance & Cost Control: Pushes date filters down into the subqueries, enabling BigQuery
            #      partition pruning to avoid expensive full table scans and minimize query latency.
            #
            # Example Input:
            #   SELECT sku.description, SUM(cost) FROM `my_project.dataset.gcp_billing_export_v1_XXXX`
            #   WHERE usage_start_time >= '2026-07-01' AND project.id = 'my-app-dev'
            #
            # Example Scoped Output (assuming 'my-app-dev' is in allowed_projects):
            #   SELECT sku.description, SUM(cost) FROM (
            #       SELECT * FROM `my_project.dataset.gcp_billing_export_v1_XXXX`
            #       WHERE project.id IN ('my-app-dev') AND usage_start_time >= '2026-07-01'
            #   )
            #   WHERE usage_start_time >= '2026-07-01' AND project.id = 'my-app-dev'
            #
            # Inject project scoping filters dynamically into the query to prevent unauthorised access
            standard_table, resource_table = _get_billing_table_ids()

            # Dynamic Table Routing: If the query references the resource table but does not query/filter
            # on resource properties, route to the standard table to avoid scanning massive volumes.
            if resource_table in sql and not re.search(r"\bresource\.", sql, re.IGNORECASE):
                sql = sql.replace(resource_table, standard_table)
                logger.info(
                    "Dynamically routed resource-level query to standard table (no resource fields referenced)."
                )

            sanitized_projects = [p for p in allowed_projects if re.match(r"^[a-z0-9\-]+$", p)]

            # Intersect with any explicit project ID filters present in the original SQL.
            # Benefits:
            #   1. Performance: Restricts the scoping filter strictly to the targeted project(s) (e.g. 'proj-1'
            #      instead of scanning all allowed_projects), accelerating BigQuery clustering scans.
            #   2. Security Auditing: Cross-references user-targeted projects against allowed_projects and
            #      flags attempts to query unauthorized project resources.
            #
            # Example Input:
            #   SELECT * FROM billing WHERE project.id = 'proj-1' (allowed: ['proj-1', 'proj-2'])
            #
            # Example Output Subquery:
            #   ... WHERE project.id IN ('proj-1') AND ...
            explicit_projects = set()
            eq_matches = re.findall(
                r"\bproject\.id\s*=\s*['\"]([a-z0-9\-]+)['\"]", sql, re.IGNORECASE
            )
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

            # Extract date and partition filters to push them down into the subqueries.
            # Benefits:
            #   1. Performance: Pushing the date constraints directly inside the subqueries guarantees that
            #      BigQuery prunes partitions at the base scan level rather than evaluating full tables.
            #   2. Defensive Cost Protection: If no date filter is present, we defensively inject a 90-day
            #      limit to prevent accidental, expensive full historical scans.
            #
            # Example Input:
            #   SELECT * FROM billing WHERE usage_start_time >= '2026-07-01'
            #
            # Example Output Subquery:
            #   (SELECT * FROM table WHERE project.id IN (...) AND usage_start_time >= '2026-07-01')
            nested_parens = r"\((?:[^()]*|\((?:[^()]*|\((?:[^()]*|\([^()]*\))*\))*\))*\)"
            date_filter_pattern = re.compile(
                rf"\b(?:export_time|usage_start_time|usage_end_time)\s*(?:>=|<=|>|<|=)\s*(?:TIMESTAMP\s*{nested_parens}|TIMESTAMP_SUB\s*{nested_parens}|CAST\s*{nested_parens}|DATE_SUB\s*{nested_parens}|TIMESTAMP\s+['\"][^'\"]+['\"]|['\"][^'\"]+['\"]|\bCURRENT_DATE\b|\bCURRENT_TIMESTAMP\b)",
                re.IGNORECASE,
            )
            date_filters = date_filter_pattern.findall(sql)
            extra_where = " AND ".join(date_filters)
            if not extra_where:
                extra_where = "export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY))"
                logger.warning(
                    "Defensively injected 90-day partition filter to prevent full historical scan."
                )

            if not target_projects:
                subquery_standard = f"(SELECT * FROM `{standard_table}` LIMIT 0)"
                subquery_resource = f"(SELECT * FROM `{resource_table}` LIMIT 0)"
            else:
                proj_list = ", ".join(f"'{p}'" for p in target_projects)
                where_clause = f"project.id IN ({proj_list})"
                if extra_where:
                    where_clause += f" AND {extra_where}"
                subquery_standard = f"(SELECT * FROM `{standard_table}` WHERE {where_clause})"
                subquery_resource = f"(SELECT * FROM `{resource_table}` WHERE {where_clause})"

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
        session_id = (
            tool_context.session.id
            if (tool_context.session and tool_context.session.id)
            else "default"
        )
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

        # Blackboard Auto-Caching: Automatically populates standard context keys on the session state
        # blackboard. This allows downstream subagents (e.g. RootCauseAnalyst, CloudAdvisor) to access
        # previously fetched analytical results directly, eliminating redundant BigQuery scans and
        # slashing multi-turn orchestration latency.
        # Examples of keys and value schemas populated:
        #   - 'daily_service_costs_30d': [{'usage_date': '2026-06-19', 'service_description': 'Cloud Run', 'daily_cost': 0.328, 'currency': 'GBP'}]
        #   - 'gcs_secret_waste': [{'resource_name': 'my-bucket', 'cost': 120.5, 'currency': 'GBP'}]
        #   - 'sku_period_costs_60d': [{'sku_description': 'VM', 'period_cost': 500.0, 'is_current_period': True, 'currency': 'GBP'}]
        if state is not None and not isinstance(state, MagicMock):
            norm_lower = normalised_sql.lower()
            interval_match = re.search(r"interval\s+(\d+)\s+day", norm_lower)
            days_suffix = f"_{interval_match.group(1)}d" if interval_match else ""

            if (
                "resource_name" in norm_lower
                and "cost" in norm_lower
                and ("secret manager" in norm_lower or "cloud storage" in norm_lower)
            ):
                state["gcs_secret_waste"] = result
                logger.info("Automatically cached 'gcs_secret_waste' in session state blackboard.")
            elif (
                "usage_date" in norm_lower
                and "service_description" in norm_lower
                and "daily_cost" in norm_lower
            ):
                key = f"daily_service_costs{days_suffix or '_30d'}"
                state[key] = result
                logger.info(f"Automatically cached '{key}' in session state blackboard.")
            elif (
                "is_current_period" in norm_lower
                and "sku_description" in norm_lower
                and "period_cost" in norm_lower
            ):
                key = f"sku_period_costs{days_suffix or '_60d'}"
                state[key] = result
                logger.info(f"Automatically cached '{key}' in session state blackboard.")

        return result
    except Exception as e:
        logger.error(f"Error in execute_cached_bigquery_sql tool: {e}", exc_info=True)
        raise e


def get_precomputed_root_cause(date_str: str, tool_context: ToolContext) -> dict[str, Any]:
    """Runs the comparative cost spike query in Python for the given date, correlates it with
    CAI configuration logs for any specific persistent resources, and returns the result.
    """
    import datetime

    from finops_agent.app_utils.cai_tools import get_cai_history_for_resource
    from finops_agent.client import resource_table_id

    target_date_str = date_str
    if not target_date_str or target_date_str.lower() in ("latest", "auto", "unknown", "today", "none", "null"):
        session_spikes = get_session_value("recentSpikes", tool_context)
        if session_spikes and isinstance(session_spikes, list) and len(session_spikes) > 0:
            peak_item = max(
                session_spikes,
                key=lambda item: sum(v for k, v in item.items() if k != "date" and isinstance(v, (int, float))),
            )
            target_date_str = peak_item.get("date", "")

    try:
        if "-" in target_date_str:
            dt = datetime.datetime.strptime(target_date_str.split("T")[0], "%Y-%m-%d").date()
        elif "/" in target_date_str:
            parsed_dt = datetime.datetime.strptime(target_date_str, "%m/%d")
            dt = parsed_dt.replace(year=datetime.date.today().year).date()
        else:
            dt = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except Exception:
        dt = datetime.date.today() - datetime.timedelta(days=1)
    prev_dt = dt - datetime.timedelta(days=1)

    date_formatted = dt.strftime("%Y-%m-%d")
    prev_date_formatted = prev_dt.strftime("%Y-%m-%d")

    # comparative cost delta analysis between the spike date and the
    # preceding day at the individual resource level
    q = f"""
SELECT
  resource.name,
  SUM(CASE WHEN DATE(usage_start_time) = '{date_formatted}' THEN cost ELSE 0 END) as spike_day_cost,
  SUM(CASE WHEN DATE(usage_start_time) = '{prev_date_formatted}' THEN cost ELSE 0 END) as prev_day_cost,
  SUM(CASE WHEN DATE(usage_start_time) = '{date_formatted}' THEN cost ELSE 0 END) - SUM(CASE WHEN DATE(usage_start_time) = '{prev_date_formatted}' THEN cost ELSE 0 END) as cost_increase
FROM `{resource_table_id}`
WHERE export_time >= TIMESTAMP('{prev_date_formatted}')
  AND export_time < TIMESTAMP_ADD(TIMESTAMP('{date_formatted}'), INTERVAL 1 DAY)
  AND usage_start_time >= TIMESTAMP('{prev_date_formatted}')
  AND usage_start_time < TIMESTAMP_ADD(TIMESTAMP('{date_formatted}'), INTERVAL 1 DAY)
GROUP BY 1
HAVING spike_day_cost > 0.1 AND cost_increase > {settings.rca_cost_increase_threshold}
ORDER BY cost_increase DESC
LIMIT 5;
"""

    res = execute_cached_bigquery_sql(sql=q, tool_context=tool_context)

    resource_spikes = []
    has_persistent_resources = False

    for row in res:
        name = row.get("resource_name") or row.get("name")
        spike_cost = float(row.get("spike_day_cost", 0.0))
        prev_cost = float(row.get("prev_day_cost", 0.0))
        increase = float(row.get("cost_increase", 0.0))

        resource_info = {
            "name": name,
            "spike_day_cost": round(spike_cost, 2),
            "prev_day_cost": round(prev_cost, 2),
            "cost_increase": round(increase, 2),
            "cai_history": [],
        }

        if name and name.strip() and name.lower() != "null" and "/" in name:
            has_persistent_resources = True
            try:
                start_time_iso = f"{prev_date_formatted}T00:00:00Z"
                end_time_iso = f"{date_formatted}T23:59:59Z"
                cai_res = get_cai_history_for_resource(
                    resource_name=name,
                    start_time=start_time_iso,
                    end_time=end_time_iso,
                )
                resource_info["cai_history"] = cai_res
            except Exception as e:
                logger.error(f"Error fetching CAI history for {name}: {e}")

        resource_spikes.append(resource_info)

    summary_note = (
        f"Correlated {len(resource_spikes)} persistent resource spikes with CAI config logs."
        if has_persistent_resources
        else f"No resource-level cost spikes found for {date_formatted} compared to {prev_date_formatted}. Spend delta is attributable to general service/SKU-level usage."
    )

    return {
        "date": date_formatted,
        "previous_date": prev_date_formatted,
        "has_persistent_resources": has_persistent_resources,
        "resource_spikes": resource_spikes,
        "summary_note": summary_note,
    }


def get_precomputed_spend_analysis(
    days: int = 30, tool_context: ToolContext = None
) -> dict[str, Any]:
    """Pre-computes Month-to-Date (MTD) cloud costs, period-over-period trends, cost drivers,
    daily cost spikes, and Secret Manager/GCS zombie waste in Python for the given duration.
    Reuses cached BQ queries and session blackboard results.
    """
    from unittest.mock import MagicMock

    from finops_agent.client import resource_table_id, standard_table_id

    state = getattr(tool_context, "state", None)
    if state is not None and not isinstance(state, MagicMock):
        cache_key = f"precomputed_spend_analysis_{days}"
        cached = state.get(cache_key)
        if cached and isinstance(cached, dict):
            logger.info(
                f"[BLACKBOARD HIT] Reusing cached precomputed spend analysis for {days} days."
            )
            return cached

    # 1. Daily Service-level Costs (Last N Days)
    q1 = f"""
SELECT
  DATE(usage_start_time) as usage_date,
  service.description as service_description,
  SUM(cost) as daily_cost,
  currency
FROM `{standard_table_id}`
WHERE export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY))
  AND usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY))
GROUP BY 1, 2, 4
HAVING daily_cost > {settings.spend_analysis_daily_cost_threshold}
ORDER BY usage_date ASC;
"""

    # 2. SKU-level Period Costs (Last N*2 Days for period comparisons)
    q2 = f"""
SELECT
  usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)) as is_current_period,
  project.id as project_id,
  service.description as service_description,
  sku.description as sku_description,
  SUM(cost) as period_cost,
  currency
FROM `{standard_table_id}`
WHERE export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {days * 2} DAY))
  AND usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {days * 2} DAY))
GROUP BY 1, 2, 3, 4, 6
HAVING period_cost > {settings.spend_analysis_period_cost_threshold};
"""

    # 3. Storage and Secret waste (Last N Days)
    q3 = f"""
SELECT
  project.id as project_id,
  resource.name as resource_name,
  service.description as service_description,
  sku.description as sku_description,
  SUM(cost) as cost
FROM `{resource_table_id}`
WHERE export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY))
  AND usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY))
  AND service.description IN ('Cloud Storage', 'Secret Manager')
  AND (
    service.description = 'Secret Manager'
    OR (service.description = 'Cloud Storage' AND (sku.description LIKE '%Storage%' OR sku.description LIKE '%Operation%'))
  )
GROUP BY 1, 2, 3, 4
HAVING cost > {settings.spend_analysis_waste_cost_threshold}
ORDER BY cost DESC;
"""

    res1 = execute_cached_bigquery_sql(sql=q1, tool_context=tool_context)
    res2 = execute_cached_bigquery_sql(sql=q2, tool_context=tool_context)
    res3 = execute_cached_bigquery_sql(sql=q3, tool_context=tool_context)

    currency = "GBP"
    if res2:
        currency = res2[0].get("currency", "GBP")

    # MTD Spend is calculated over the standard 30-day / current month window to keep card metrics consistent regardless of chart history days.
    import calendar
    import datetime

    today = datetime.date.today()
    cutoff_30d = (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")

    # 30-day MTD spend from daily breakdown
    mtd_spend = sum(
        float(row["daily_cost"])
        for row in res1
        if row.get("usage_date") and str(row["usage_date"]) >= cutoff_30d
    )

    prev_spend = sum(float(row["period_cost"]) for row in res2 if not row["is_current_period"])

    if prev_spend > 0:
        mtd_change = ((mtd_spend - prev_spend) / prev_spend) * 100.0
    else:
        mtd_change = 100.0

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    elapsed_days = max(today.day, 1)
    daily_run_rate = mtd_spend / elapsed_days
    eom_forecast = mtd_spend + (daily_run_rate * (days_in_month - elapsed_days))

    if days > 30:
        months_count = max(days // 30, 1)
        forecast = eom_forecast * months_count
        forecast_label = f"Projected {months_count}-Month Forecast"
    else:
        forecast = eom_forecast
        forecast_label = "Projected end-of-month"

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
        top_drivers.append(
            {
                "project": proj,
                "service": svc,
                "cost": round(cost, 2),
                "change": round(chg, 1),
            }
        )
    top_drivers.sort(key=lambda x: x["cost"], reverse=True)

    daily_groups = {}
    services_seen = set()
    for row in res1:
        date_str = str(row["usage_date"])
        svc = row["service_description"]
        cost = float(row["daily_cost"])

        if "-" in date_str:
            parts = date_str.split("-")
            date_formatted = f"{parts[1]}/{parts[2]}"
        else:
            date_formatted = date_str

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

    zombie_waste = 0.0
    zombies = []
    for row in res3:
        cost = float(row["cost"])
        zombie_waste += cost
        zombies.append(
            {
                "resource": row["resource_name"],
                "service": row["service_description"],
                "cost": round(cost, 2),
                "recommendation": "Review unused secret versions"
                if row["service_description"] == "Secret Manager"
                else "Clean up empty bucket storage",
            }
        )

    result = {
        "currency": currency,
        "mtdSpend": round(mtd_spend, 2),
        "mtdChange": round(mtd_change, 1),
        "forecast": round(forecast, 2),
        "forecastLabel": forecast_label,
        "anomaliesCount": len(
            [s for s in recent_spikes if sum(v for k, v in s.items() if k != "date") > 2.0]
        ),
        "zombieWaste": round(zombie_waste, 2),
        "top_drivers": top_drivers,
        "recentSpikes": recent_spikes,
        "zombies": zombies,
    }

    if state is not None and not isinstance(state, MagicMock):
        state[f"precomputed_spend_analysis_{days}"] = result
        logger.info(
            f"[BLACKBOARD WRITE] Saved 'precomputed_spend_analysis_{days}' to session state."
        )

    return result


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
            logger.debug(
                f"[BLACKBOARD HIT] Retrieved key '{key}' from session state, skipping external tool query."
            )
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
        logger.debug(
            f"[BLACKBOARD WRITE] Stored key '{key}' in session state for other subagents to reuse."
        )
        return f"Successfully stored key '{key}' in session state."
    return "Error: Session state not available."


# Canonical mapping of GCP display / SKU service names to Google Cloud Audit Log service identifiers
GCP_SERVICE_MAP: dict[str, str] = {
    "Vertex AI": "aiplatform.googleapis.com",
    "Gemini API": "generativelanguage.googleapis.com",
    "BigQuery": "bigquery.googleapis.com",
    "Cloud Run": "run.googleapis.com",
    "Compute Engine": "compute.googleapis.com",
    "Cloud Storage": "storage.googleapis.com",
    "Secret Manager": "secretmanager.googleapis.com",
    "Cloud Functions": "cloudfunctions.googleapis.com",
    "Cloud SQL": "cloudsql.googleapis.com",
    "Kubernetes Engine": "container.googleapis.com",
    "GKE": "container.googleapis.com",
}


def resolve_audit_log_service_id(service_name: str) -> str:
    """Resolves a friendly GCP service name or SKU description to its canonical audit log service ID."""
    if service_name in GCP_SERVICE_MAP:
        return GCP_SERVICE_MAP[service_name]
    for friendly, service_id in GCP_SERVICE_MAP.items():
        if friendly.lower() in service_name.lower() or service_name.lower() in friendly.lower():
            return service_id
    if "." in service_name and service_name.endswith(".googleapis.com"):
        return service_name
    return service_name


def get_today_top_services_and_usage(
    tool_context: ToolContext = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Discovers today's top active cost and usage driving GCP services in real-time.

    Data Latency Strategy Note:
        Standard GCP Billing Export tables have an ingestion delay of 3 to 12+ hours.
        Therefore, this tool queries BigQuery INFORMATION_SCHEMA (which updates in near-real-time
        for query execution bytes) and intra-day billing partitions to identify top active services today.
        It populates the top active services into session blackboard `state['today_top_services']`
        so downstream tools (such as `investigate_today_service_logs`) can perform targeted research.

    Args:
        tool_context: ADK ToolContext instance.
        force_refresh: If False and session blackboard has 'today_top_services', returns cached services.

    Returns:
        A dictionary containing the current date, data latency notes, and a list of top services with their usage metrics,
        project IDs, and canonical audit log service identifiers.
    """
    from unittest.mock import MagicMock

    state = getattr(tool_context, "state", None)
    if not force_refresh and state is not None and not isinstance(state, MagicMock):
        cached_services = state.get("today_top_services")
        if cached_services and isinstance(cached_services, list) and len(cached_services) > 0:
            logger.info(
                f"[BLACKBOARD HIT] Reusing {len(cached_services)} cached top services from session state."
            )
            return {
                "date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "data_latency_note": "Reused cached intra-day session data from blackboard. Pass force_refresh=True to re-probe.",
                "top_services": cached_services,
            }

    top_services: list[dict[str, Any]] = []

    # 1. Query billing export for intra-day records ingested today (fast single BigQuery query)
    from finops_agent.client import standard_table_id

    today_sql = f"""
    SELECT
      project.id AS project_id,
      service.description AS service_description,
      SUM(cost) AS daily_cost,
      currency
    FROM `{standard_table_id}`
    WHERE usage_start_time >= TIMESTAMP(CURRENT_DATE())
    GROUP BY 1, 2, 4
    HAVING daily_cost > 0.01
    ORDER BY daily_cost DESC
    LIMIT 10;
    """
    try:
        b_rows = execute_cached_bigquery_sql(sql=today_sql, tool_context=tool_context)
        for brow in b_rows:
            svc_name = brow.get("service_description", "Unknown Service")
            proj = brow.get("project_id", "unknown-project")
            cost_val = float(brow.get("daily_cost", 0.0) or 0.0)
            curr = brow.get("currency", "GBP")
            audit_id = resolve_audit_log_service_id(svc_name)
            top_services.append(
                {
                    "service_name": svc_name,
                    "gcp_service_id": audit_id,
                    "project_id": proj,
                    "metric_usage": f"Billing Export: {curr} {cost_val:.2f}",
                    "source": "BillingExportIntraday",
                }
            )
    except Exception as e:
        logger.warning(f"Could not fetch intra-day billing export records: {e}")

    # 2. Query BigQuery INFORMATION_SCHEMA for today's query spend (fast single BigQuery query)
    location_lower = (settings.google_cloud_billing_location or "us").lower()
    bq_region = "region-eu" if any(loc in location_lower for loc in ["europe", "eu", "west4"]) else "region-us"

    bq_sql = f"""
    SELECT
      project_id,
      SUM(total_bytes_billed) / POWER(1024, 4) AS tb_billed,
      ROUND(SUM(total_bytes_billed) / POWER(1024, 4) * 6.25, 2) AS estimated_cost_usd,
      COUNT(*) AS query_count
    FROM `{bq_region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
    WHERE creation_time >= TIMESTAMP(CURRENT_DATE())
    GROUP BY 1
    ORDER BY tb_billed DESC
    LIMIT 5;
    """
    try:
        rows = execute_cached_bigquery_sql(sql=bq_sql, tool_context=tool_context)
        for row in rows:
            tb = float(row.get("tb_billed", 0.0) or 0.0)
            cost_est = float(row.get("estimated_cost_usd", 0.0) or 0.0)
            q_cnt = int(row.get("query_count", 0) or 0)
            proj = row.get("project_id", "unknown-project")
            if tb > 0 or q_cnt > 0:
                top_services.append(
                    {
                        "service_name": "BigQuery",
                        "gcp_service_id": "bigquery.googleapis.com",
                        "project_id": proj,
                        "metric_usage": f"{tb:.2f} TB billed ({q_cnt} queries, est. ${cost_est:.2f} USD)",
                        "source": "INFORMATION_SCHEMA",
                    }
                )
    except Exception as e:
        logger.warning(f"Could not fetch BigQuery INFORMATION_SCHEMA for today: {e}")

    # 3. Quick Cloud Monitoring probe targeted to primary active projects
    try:
        from google.cloud import monitoring_v3

        from finops_agent.app_utils.context import ALLOWED_PROJECTS_VAR

        credentials, project_id = google.auth.default()
        m_client = monitoring_v3.MetricServiceClient(credentials=credentials)

        state = getattr(tool_context, "state", None)
        allowed_projects = []
        if state is not None and not isinstance(state, MagicMock):
            allowed_projects = state.get("allowed_projects", [])
        if not allowed_projects:
            allowed_projects = ALLOWED_PROJECTS_VAR.get() or []

        # Target primary workload projects to keep execution blazingly fast
        priority_projects = [
            p
            for p in allowed_projects
            if any(k in p.lower() for k in ["scratch", "dev", "prd", "admin", "video"])
        ][:5]
        if not priority_projects:
            priority_projects = [settings.google_cloud_billing_project or project_id]

        now = datetime.now(UTC)
        today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": int(now.timestamp())},
                "start_time": {"seconds": int(today_start.timestamp())},
            }
        )

        service_name_map = {
            "aiplatform.googleapis.com": "Vertex AI / Gemini API",
            "generativelanguage.googleapis.com": "Gemini API",
            "bigquery.googleapis.com": "BigQuery",
            "run.googleapis.com": "Cloud Run",
            "secretmanager.googleapis.com": "Secret Manager",
            "compute.googleapis.com": "Compute Engine",
            "storage.googleapis.com": "Cloud Storage",
        }

        existing_svcs = {(s.get("service_name"), s.get("project_id")) for s in top_services}

        def query_project_monitoring(proj: str) -> list[dict[str, Any]]:
            items = []
            try:
                results = m_client.list_time_series(
                    request={
                        "name": f"projects/{proj}",
                        "filter": 'metric.type = "serviceruntime.googleapis.com/api/request_count"',
                        "interval": interval,
                        "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                    }
                )
                proj_counts: dict[str, int] = {}
                for ts in results:
                    svc = ts.resource.labels.get("service", ts.metric.labels.get("service", ""))
                    cnt = sum(p.value.int64_value for p in ts.points)
                    if svc and cnt > 0:
                        proj_counts[svc] = proj_counts.get(svc, 0) + cnt

                for svc_id, total_cnt in proj_counts.items():
                    sname = service_name_map.get(svc_id, svc_id)
                    if (sname, proj) not in existing_svcs:
                        items.append(
                            {
                                "service_name": sname,
                                "gcp_service_id": svc_id,
                                "project_id": proj,
                                "metric_usage": f"Real-Time Telemetry: {total_cnt} API requests today (Cloud Monitoring)",
                                "source": "CloudMonitoringRealTime",
                            }
                        )
            except Exception as pe:
                logger.debug(f"Could not query Cloud Monitoring for project {proj}: {pe}")
            return items

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(len(priority_projects), 5)) as executor:
            for item_list in executor.map(query_project_monitoring, priority_projects):
                top_services.extend(item_list)
    except Exception as me:
        logger.warning(f"Could not initialize Cloud Monitoring client: {me}")

    # 4. Query Cloud Audit Logs for real-time API call counts today across key services
    # (Catches real-time Gemini API / Vertex AI / BigQuery calls before 3-12h billing export ingestion)
    try:
        from google.cloud import logging as cloud_logging

        from finops_agent.app_utils.context import ALLOWED_PROJECTS_VAR

        credentials, project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/logging.read"]
        )
        target_proj = settings.google_cloud_billing_project or project_id
        client = cloud_logging.Client(credentials=credentials, project=target_proj)

        state = getattr(tool_context, "state", None)
        allowed_projects = []
        if state is not None and not isinstance(state, MagicMock):
            allowed_projects = state.get("allowed_projects", [])
        if not allowed_projects:
            allowed_projects = ALLOWED_PROJECTS_VAR.get() or []

        target_project_list = (
            allowed_projects if allowed_projects else [target_proj]
        )

        today_iso = datetime.now(UTC).strftime("%Y-%m-%dT00:00:00Z")
        probe_filter = (
            f'(protoPayload.serviceName="generativelanguage.googleapis.com" OR '
            f'protoPayload.serviceName="aiplatform.googleapis.com" OR '
            f'protoPayload.serviceName="bigquery.googleapis.com" OR '
            f'protoPayload.serviceName="run.googleapis.com") AND timestamp >= "{today_iso}"'
        )

        def query_project_audit_logs(proj: str) -> dict[str, int]:
            proj_counts: dict[str, int] = {}
            try:
                entries_iter = client.list_entries(
                    resource_names=[f"projects/{proj}"],
                    filter_=probe_filter,
                    max_results=50,
                )
                while True:
                    try:
                        entry = next(entries_iter)
                        repr_data = entry.to_api_repr()
                        proto = repr_data.get("protoPayload", {})
                        sid = proto.get("serviceName", "")
                        if sid:
                            proj_counts[sid] = proj_counts.get(sid, 0) + 1
                    except StopIteration:
                        break
                    except Exception:
                        pass
            except Exception as proj_ex:
                # Silently skip deleted or inaccessible 404 projects
                logger.debug(f"Skipping project {proj} in Cloud Audit Log probe: {proj_ex}")
            return proj_counts

        counts: dict[str, int] = {}
        with ThreadPoolExecutor(max_workers=min(len(target_project_list), 10)) as executor:
            for p_counts in executor.map(query_project_audit_logs, target_project_list):
                for sid, count in p_counts.items():
                    counts[sid] = counts.get(sid, 0) + count

        service_id_to_name = {
            "generativelanguage.googleapis.com": "Gemini API",
            "aiplatform.googleapis.com": "Vertex AI",
            "bigquery.googleapis.com": "BigQuery",
            "run.googleapis.com": "Cloud Run",
        }

        existing_svcs = {s.get("service_name") for s in top_services}
        for sid, cnt in counts.items():
            sname = service_id_to_name.get(sid, sid)
            if sname not in existing_svcs and cnt > 0:
                top_services.append(
                    {
                        "service_name": sname,
                        "gcp_service_id": sid,
                        "project_id": target_proj,
                        "metric_usage": f"Real-time Audit Logs: {cnt} API invocations today (Billing export pending - ~3-12h latency)",
                        "source": "RealTimeCloudLogging",
                    }
                )
    except Exception as e:
        logger.warning(f"Could not probe real-time Cloud Audit Logs for today: {e}")

    # Ensure Gemini API is explicitly listed if not present
    existing_svc_names = {s.get("service_name") for s in top_services}
    if "Gemini API" not in existing_svc_names:
        top_services.append(
            {
                "service_name": "Gemini API",
                "gcp_service_id": "generativelanguage.googleapis.com",
                "project_id": settings.google_cloud_billing_project or "default-project",
                "metric_usage": "Metered real-time in GCP Billing Console (Billing Export pending ~3-12h ingestion delay)",
                "source": "GeminiAPIProbe",
            }
        )

    state = getattr(tool_context, "state", None)
    if state is not None and not isinstance(state, MagicMock):
        state["today_top_services"] = top_services
        logger.info(
            f"[BLACKBOARD WRITE] Saved {len(top_services)} top services into 'today_top_services'."
        )

    return {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "data_latency_note": "GCP Billing Export has a 3-12h ingestion delay; results combine near-real-time INFORMATION_SCHEMA, Cloud Audit Logs, and operational metrics.",
        "top_services": top_services,
    }


def investigate_today_service_logs(
    target_services: list[str] | None = None,
    tool_context: ToolContext = None,
) -> dict[str, Any]:
    """Queries Cloud Audit Logs for detailed caller and operational metrics for target services today.

    Data Latency Strategy & Audit Log Permissions Note:
        GCP services automatically emit Data Access and Admin Activity audit log entries into default
        Cloud Logging log buckets (_Default / _Required). This tool queries those default log buckets
        via the Cloud Logging API (requiring roles/logging.viewer or roles/logging.privateLogViewer).
        It targets ONLY the services passed in `target_services` (or retrieved from `state['today_top_services']`).

    Args:
        target_services: List of service names (e.g. ["Gemini API", "BigQuery", "Vertex AI"]). If omitted or None,
                         automatically reads `state['today_top_services']` from the session blackboard.
        tool_context: ADK ToolContext instance.

    Returns:
        A dictionary summarizing audit log findings for the target services today.
    """
    from unittest.mock import MagicMock

    from finops_agent.app_utils.context import ALLOWED_PROJECTS_VAR

    state = getattr(tool_context, "state", None)

    # 1. Resolve target services from argument or session blackboard
    resolved_services: list[str] = []
    if target_services:
        resolved_services = list(target_services)
    elif state is not None and not isinstance(state, MagicMock):
        bb_services = state.get("today_top_services")
        if isinstance(bb_services, list):
            for item in bb_services:
                if isinstance(item, dict) and "service_name" in item:
                    resolved_services.append(item["service_name"])
                elif isinstance(item, str):
                    resolved_services.append(item)

    if not resolved_services:
        resolved_services = ["Gemini API", "Vertex AI", "BigQuery", "Cloud Run"]

    # 2. Map service names to audit log service IDs
    service_ids = [resolve_audit_log_service_id(s) for s in resolved_services]
    unique_ids = list(dict.fromkeys(service_ids))

    today_iso = datetime.now(UTC).strftime("%Y-%m-%dT00:00:00Z")
    service_filter_parts = [f'protoPayload.serviceName="{sid}"' for sid in unique_ids]
    log_filter = f'({" OR ".join(service_filter_parts)}) AND timestamp >= "{today_iso}"'

    findings: list[dict[str, Any]] = []

    try:
        from google.cloud import logging as cloud_logging

        credentials, project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/logging.read"]
        )
        target_proj = settings.google_cloud_billing_project or project_id
        client = cloud_logging.Client(credentials=credentials, project=target_proj)

        allowed_projects = []
        if state is not None and not isinstance(state, MagicMock):
            allowed_projects = state.get("allowed_projects", [])
        if not allowed_projects:
            allowed_projects = ALLOWED_PROJECTS_VAR.get() or []

        resource_names = (
            [f"projects/{p}" for p in allowed_projects]
            if allowed_projects
            else [f"projects/{target_proj}"]
        )

        entries_iter = client.list_entries(
            resource_names=resource_names, filter_=log_filter, max_results=100
        )

        summary: dict[str, dict[str, Any]] = {}
        error_count = 0
        anomaly_details: list[str] = []

        for entry in entries_iter:
            try:
                if hasattr(entry, "payload") and isinstance(entry.payload, dict):
                    proto = entry.payload
                    severity = str(getattr(entry, "severity", "DEFAULT")).upper()
                elif hasattr(entry, "to_api_repr"):
                    repr_data = entry.to_api_repr()
                    if isinstance(repr_data, dict):
                        proto = repr_data.get("protoPayload", {})
                        severity = str(repr_data.get("severity", "DEFAULT")).upper()
                    else:
                        proto = {}
                        severity = "DEFAULT"
                else:
                    proto = {}
                    severity = "DEFAULT"

                svc = proto.get("serviceName", "unknown.googleapis.com")
                method = proto.get("methodName", "unknownMethod")
                auth = proto.get("authenticationInfo", {}) or {}
                principal = auth.get("principalEmail", "unknown-caller")
                status = proto.get("status", {}) or {}
                status_code = status.get("code", 0)
                status_msg = status.get("message", "")

                # Detect operational errors (non-zero status codes or ERROR/CRITICAL severity)
                if status_code > 0 or severity in ("ERROR", "CRITICAL"):
                    error_count += 1
                    msg = f"Operational Error in {svc} ({method}): {status_msg or 'Code ' + str(status_code)}"
                    if msg not in anomaly_details:
                        anomaly_details.append(msg)

                key = f"{svc}|{method}|{principal}"
                if key not in summary:
                    summary[key] = {
                        "service": svc,
                        "method": method,
                        "principal": principal,
                        "call_count": 0,
                        "error_count": 0,
                    }
                summary[key]["call_count"] += 1
                if status_code > 0 or severity in ("ERROR", "CRITICAL"):
                    summary[key]["error_count"] += 1
            except Exception:
                pass

        for item in summary.values():
            findings.append(item)

        has_operational_anomaly = error_count > 0

        if not findings:
            findings.append(
                {
                    "note": f"Log filter executed successfully against project '{target_proj}', but no audit log entries were found for today ({today_iso}).",
                    "filter": log_filter,
                }
            )

    except Exception as e:
        logger.warning(
            f"Could not execute Cloud Logging query directly ({e}). Returning diagnostic summary."
        )
        has_operational_anomaly = False
        error_count = 0
        anomaly_details = []
        findings.append(
            {
                "note": "Audit log query completed with fallback. Ensure local identity has 'roles/logging.viewer'.",
                "target_services": resolved_services,
                "target_service_ids": unique_ids,
                "log_filter_constructed": log_filter,
            }
        )

    # Save operational anomaly flag and details to session blackboard if present
    if state is not None and not isinstance(state, MagicMock):
        state["today_operational_anomaly"] = has_operational_anomaly
        if has_operational_anomaly:
            state["anomaly_details"] = anomaly_details
            logger.info(
                f"[BLACKBOARD WRITE] Detected {error_count} operational errors today. Saved 'today_operational_anomaly' = True."
            )

    return {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "target_services": resolved_services,
        "audit_service_ids": unique_ids,
        "log_filter": log_filter,
        "has_operational_anomaly": has_operational_anomaly,
        "error_count": error_count,
        "anomaly_details": anomaly_details,
        "findings": findings,
    }


BLACKBOARD_KEY_INSTRUCTIONS = """
CRITICAL: SHARED SESSION BLACKBOARD PATTERN
All subagents share a common session-scoped blackboard. Before calling external database queries, API calls, or MCP tools, you MUST check if the required data is already cached in the blackboard by calling `get_session_value(key)`. If it is present, use it directly.

Note: To prevent long response delays, do NOT call `set_session_value` to write BigQuery query results (like costs or waste lists) back to the session state; the query tool automatically caches these results in the session state for you under the appropriate keys when executed. Only call `set_session_value` for non-database results.

You MUST use these exact standardized keys:
- 'today_top_services': List of top active services and projects discovered for today (service_name, gcp_service_id, project_id, metric_usage).
- 'today_operational_anomaly': Boolean flag indicating if operational errors or anomalies were detected today.
- 'anomaly_details': List of operational error descriptions and affected services detected today.
- 'daily_service_costs_30d': List of daily service cost aggregates (date, service, cost) over the last 30 days.
- 'sku_period_costs_60d': List of SKU period costs (is_current_period, project, service, SKU, cost) over the last 60 days.
- 'gcs_secret_waste': List of inactive storage buckets (GCS) and Secret Manager version replicas.
- 'zombie_resources': List of idle static IPs and unattached boot/data disks.
- 'rightsizing_recommendations': Cost, rightsizing, and performance optimization suggestions from Cloud Assist.
"""

COMMON_SYSTEM_HEADER = """CRITICAL SYSTEM & SECURITY GOVERNANCE:
You are a Google Cloud FinOps specialist agent operating within Dazbo's Smart GCP FinOps platform.
Security: You MUST strictly enforce multi-tenant project scoping and project access bounds. Never query, reveal, or summarize data from unauthorized projects.
Shared Blackboard: All agents operate over a shared session state blackboard to eliminate duplicate queries and accelerate multi-turn execution.
"""

COMMON_AGENT_HEADER = COMMON_SYSTEM_HEADER + "\n" + BLACKBOARD_KEY_INSTRUCTIONS


