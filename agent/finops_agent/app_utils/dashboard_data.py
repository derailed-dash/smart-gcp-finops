"""Dashboard metrics aggregation and telemetry compiler for the FinOps UI.

What:
    Compiles summary metrics, cost trends, spending forecasts, budget alerts, cost anomalies, and zombie
    resource breakdowns for display in the React frontend dashboard.

Why:
    Serves the Backend for Frontend (BFF) API with aggregated, pre-filtered FinOps data so the UI can quickly
    render rich visual charts and action cards without executing complex SQL logic client-side.

How:
    Executes optimized BigQuery SQL queries against GCP billing export tables, enforces user project permission
    scoping filters via context variables, caches query results in memory, and merges Cloud Asset Inventory data.
"""

import calendar
import logging
import re
import statistics
import threading
import time
from datetime import datetime, timedelta

from google.auth import default
from google.cloud import bigquery

from finops_agent.app_utils.zombie_tools import list_zombie_resources
from finops_agent.config import settings

logger = logging.getLogger(__name__)

# Local query cache for dashboard data to avoid duplicate queries
_DASHBOARD_QUERY_CACHE: dict[str, tuple[float, list]] = {}
_DASHBOARD_CACHE_LOCK = threading.Lock()
DASHBOARD_CACHE_TTL = 300  # 5 minutes


def execute_dashboard_query(client: bigquery.Client, sql: str) -> list:
    """Executes a query and caches the result locally for 5 minutes."""
    now = time.time()
    normalised_sql = re.sub(r"\s+", " ", sql).strip()

    with _DASHBOARD_CACHE_LOCK:
        if normalised_sql in _DASHBOARD_QUERY_CACHE:
            expiry, result = _DASHBOARD_QUERY_CACHE[normalised_sql]
            if now <= expiry:
                logger.debug("Dashboard query cache hit.")
                return result

    logger.debug("Dashboard query cache miss. Executing query...")
    job = client.query(sql)
    result = list(job.result())

    with _DASHBOARD_CACHE_LOCK:
        _DASHBOARD_QUERY_CACHE[normalised_sql] = (now + DASHBOARD_CACHE_TTL, result)

    return result


def classify_project(project_id: str | None) -> str:
    """Classifies a GCP project ID into dev, staging, or prod."""
    if not project_id:
        return "prod"
    p_lower = project_id.lower()
    if any(k in p_lower for k in ["-dev", "dev-", "scratch", "sandbox", "npd", "demo"]):
        return "dev"
    elif any(k in p_lower for k in ["-staging", "staging-", "stg"]):
        return "staging"
    else:
        return "prod"


def estimate_zombie_cost(zombie: dict, category: str) -> float:
    """Estimates the monthly cost of a zombie resource based on CAI details."""
    if category == "UNATTACHED_DISKS":
        # Estimate based on size if available
        attrs = zombie.get("additionalAttributes") or {}
        size_str = attrs.get("size", "")
        # Try to parse number of GB
        match = re.search(r"(\d+)\s*(?:GB|GiB)", size_str, re.IGNORECASE)
        if match:
            gb = float(match.group(1))
            return round(gb * 0.10, 2)  # Standard balanced PD is ~$0.10/GB/month
        return 40.00  # Default estimate for persistent disk if size is unknown
    elif category == "IDLE_IPS":
        return 15.00  # Idle static IP address is ~$15.00/month
    return 10.00


def get_actual_dashboard_metrics(
    allowed_projects: set[str] | None = None,
    client_day: int | None = None,
    client_month_days: int | None = None,
    days: int = 30,
) -> dict:
    """
    Queries BigQuery billing tables and Cloud Asset Inventory to assemble the actual
    real-time dashboard metrics payload.
    """
    # 1. Setup default fallback response in case of any failures
    fallback_response = {
        "currency": "GBP",
        "mtdSpend": 0.0,
        "mtdChange": 0.0,
        "forecast": 0.0,
        "forecastLabel": "Projected end-of-month",
        "anomaliesCount": 0,
        "zombieWaste": 0.0,
        "recentSpikes": [],
        "zombies": [],
        "explorer": [],
    }

    try:
        credentials, _ = default()
        client = bigquery.Client(
            credentials=credentials, project=settings.google_cloud_billing_project
        )
    except Exception as e:
        logger.error(f"Failed to initialize BigQuery client for dashboard data: {e}")
        return fallback_response

    billing_suffix = settings.google_cloud_billing_account.replace("-", "_")
    standard_table_id = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_v1_{billing_suffix}"

    # 0. Setup access control project filter
    project_filter = ""
    if allowed_projects is not None:
        sanitized_projects = [p for p in allowed_projects if re.match(r"^[a-z0-9\-]+$", p)]
        if not sanitized_projects:
            project_filter = "AND 1=0"
        else:
            proj_list = ", ".join(f"'{p}'" for p in sanitized_projects)
            project_filter = f"AND project.id IN ({proj_list})"

    # Get actual billing currency dynamically from standard table
    currency = "GBP"
    try:
        currency_query = f"""
        SELECT DISTINCT currency
        FROM `{standard_table_id}`
        WHERE usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY))
        {project_filter}
        LIMIT 1
        """
        cur_results = execute_dashboard_query(client, currency_query)
        if cur_results:
            currency = cur_results[0].currency or "GBP"
    except Exception as e:
        logger.error(f"Error querying dynamic currency: {e}")

    # Construct SQL Queries
    now = datetime.now()
    current_year_month = now.strftime("%Y-%m")

    month_query = f"""
    SELECT
      FORMAT_TIMESTAMP('%Y-%m', usage_start_time) as billing_month,
      SUM(cost) as monthly_cost
    FROM `{standard_table_id}`
    WHERE usage_start_time >= TIMESTAMP(DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 2 MONTH))
    {project_filter}
    GROUP BY 1
    ORDER BY billing_month DESC
    """

    daily_query = f"""
    SELECT
      DATE(usage_start_time) as usage_date,
      service.description as service_description,
      SUM(cost) as daily_cost
    FROM `{standard_table_id}`
    WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
    {project_filter}
    GROUP BY 1, 2
    HAVING daily_cost > 0.01
    ORDER BY usage_date ASC
    """

    explorer_query = f"""
    SELECT
      project.id as project_id,
      service.description as service_description,
      FORMAT_TIMESTAMP('%Y-%m', usage_start_time) as billing_month,
      SUM(cost) as monthly_cost
    FROM `{standard_table_id}`
    WHERE usage_start_time >= TIMESTAMP(DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 1 MONTH))
    {project_filter}
    GROUP BY 1, 2, 3
    HAVING monthly_cost > 0.01
    ORDER BY monthly_cost DESC
    """

    # Dispatch tasks concurrently via ThreadPoolExecutor
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_month = executor.submit(execute_dashboard_query, client, month_query)
        future_daily = executor.submit(execute_dashboard_query, client, daily_query)
        future_explorer = executor.submit(execute_dashboard_query, client, explorer_query)
        future_disks = executor.submit(list_zombie_resources, "UNATTACHED_DISKS")
        future_ips = executor.submit(list_zombie_resources, "IDLE_IPS")

        # 2. Process Month-to-Date Spend and MoM Change
        mtd_spend = 0.0
        mtd_change = 0.0
        forecast = 0.0

        try:
            month_results = future_month.result()

            costs = {
                row.billing_month: float(row.monthly_cost or 0.0)
                for row in month_results
                if row.billing_month
            }

            mtd_spend = costs.get(current_year_month, 0.0)
            prev_month = now.replace(day=1) - timedelta(days=1)
            prev_year_month = prev_month.strftime("%Y-%m")
            prev_mtd_spend = costs.get(prev_year_month, 0.0)

            if prev_mtd_spend > 0:
                mtd_change = round(((mtd_spend - prev_mtd_spend) / prev_mtd_spend) * 100, 1)

            days_in_month = (
                client_month_days
                if client_month_days is not None
                else calendar.monthrange(now.year, now.month)[1]
            )

            if client_day is not None:
                elapsed_days = max(int(client_day), 1)
            else:
                elapsed_days = max(now.day, 1)
                try:
                    telemetry_day_query = f"""
                    SELECT EXTRACT(DAY FROM MAX(usage_start_time)) as max_day
                    FROM `{standard_table_id}`
                    WHERE usage_start_time >= TIMESTAMP(DATE_TRUNC(CURRENT_DATE(), MONTH))
                    {project_filter}
                    """
                    day_results = execute_dashboard_query(client, telemetry_day_query)
                    if day_results and day_results[0].max_day is not None:
                        elapsed_days = max(int(day_results[0].max_day), 1)
                        elapsed_days = min(elapsed_days, days_in_month)
                except Exception as e:
                    logger.error(f"Error querying telemetry elapsed days for forecast: {e}")

            forecast = round((mtd_spend / elapsed_days) * days_in_month, 2)
            mtd_spend = round(mtd_spend, 2)
        except Exception as e:
            logger.error(f"Error querying monthly costs: {e}")

        # 3. Process Daily Costs & Statistical Anomaly Detection
        recent_spikes = []
        top_services = []
        anomalies_count = 0

        try:
            daily_results = future_daily.result()

            service_totals = {}
            for row in daily_results:
                srv = row.service_description or "Unknown Service"
                cost = float(row.daily_cost)
                service_totals[srv] = service_totals.get(srv, 0.0) + cost

            sorted_services = sorted(service_totals.items(), key=lambda x: x[1], reverse=True)
            top_n_services = [name for name, total in sorted_services[:3] if total > 0]

            daily_map = {}
            for row in daily_results:
                d_str = (
                    row.usage_date.strftime("%m/%d")
                    if hasattr(row.usage_date, "strftime")
                    else str(row.usage_date)
                )
                srv = row.service_description or "Unknown Service"
                cost = float(row.daily_cost)

                if d_str not in daily_map:
                    daily_map[d_str] = {}
                daily_map[d_str][srv] = daily_map[d_str].get(srv, 0.0) + cost

            sorted_dates = sorted(daily_map.keys())
            for d_str in sorted_dates:
                day_costs = daily_map[d_str]
                row_dict = {"date": d_str}

                other_sum = 0.0
                for srv, cost in day_costs.items():
                    if srv in top_n_services:
                        row_dict[srv] = round(cost, 2)
                    else:
                        other_sum += cost

                for srv in top_n_services:
                    if srv not in row_dict:
                        row_dict[srv] = 0.0

                if other_sum > 0:
                    row_dict["Other"] = round(other_sum, 2)
                elif "Other" in top_services or len(sorted_services) > 3:
                    row_dict["Other"] = 0.0

                recent_spikes.append(row_dict)

            top_services = list(top_n_services)
            if any("Other" in r for r in recent_spikes):
                top_services.append("Other")

            daily_totals = []
            for r in recent_spikes:
                total = sum(r[k] for k in r if k != "date")
                daily_totals.append(total)

            if len(daily_totals) >= 5:
                median_val = statistics.median(daily_totals[:-1])
                baseline_days = [val for val in daily_totals[:-1] if val >= median_val * 0.25]
                if len(baseline_days) >= 3:
                    mean = statistics.mean(baseline_days)
                    std_dev = statistics.stdev(baseline_days)
                else:
                    mean = statistics.mean(daily_totals[:-1])
                    std_dev = statistics.stdev(daily_totals[:-1])

                threshold = mean + 1.2 * std_dev if std_dev > 0 else mean * 1.15

                for total in daily_totals:
                    if total > threshold:
                        anomalies_count += 1

        except Exception as e:
            logger.error(f"Error querying daily costs or detecting anomalies: {e}")

        # 4. Process Zombie Resources
        zombies = []
        zombie_waste = 0.0

        try:
            unattached_disks = future_disks.result()
            for item in unattached_disks:
                proj = item.get("project", "").split("/")[-1] if item.get("project") else "unknown"
                if allowed_projects is not None and proj not in allowed_projects:
                    continue

                cost = estimate_zombie_cost(item, "UNATTACHED_DISKS")
                zombie_waste += cost
                name = item.get("displayName") or item.get("name", "").split("/")[-1]

                zombies.append(
                    {
                        "id": item.get("name", ""),
                        "name": name,
                        "type": "Persistent Disk",
                        "project": proj,
                        "size": (item.get("additionalAttributes") or {}).get("size", "Unknown Size"),
                        "cost": cost,
                        "status": "UNATTACHED",
                    }
                )

            idle_ips = future_ips.result()
            for item in idle_ips:
                proj = item.get("project", "").split("/")[-1] if item.get("project") else "unknown"
                if allowed_projects is not None and proj not in allowed_projects:
                    continue

                cost = estimate_zombie_cost(item, "IDLE_IPS")
                zombie_waste += cost
                name = item.get("displayName") or item.get("name", "").split("/")[-1]

                zombies.append(
                    {
                        "id": item.get("name", ""),
                        "name": name,
                        "type": "Static External IP",
                        "project": proj,
                        "size": "N/A",
                        "cost": cost,
                        "status": "UNASSIGNED",
                    }
                )

            zombie_waste = round(zombie_waste, 2)
        except Exception as e:
            logger.error(f"Error listing CAI zombie resources: {e}")

        # 5. Process Cost Explorer Breakdown
        explorer = []
        try:
            explorer_results = future_explorer.result()

            explorer_data_map = {}
            for row in explorer_results:
                proj_id = row.project_id or "unknown-project"
                service_desc = row.service_description or "Unknown Service"
                month = row.billing_month
                cost = float(row.monthly_cost)

                key = (proj_id, service_desc)
                if key not in explorer_data_map:
                    explorer_data_map[key] = {}
                explorer_data_map[key][month] = cost

            prev_month = now.replace(day=1) - timedelta(days=1)
            prev_year_month = prev_month.strftime("%Y-%m")

            for (proj_id, service_desc), months_costs in explorer_data_map.items():
                mtd_cost = months_costs.get(current_year_month, 0.0)
                if mtd_cost <= 0:
                    continue

                prev_cost = months_costs.get(prev_year_month, 0.0)
                change = 0.0
                if prev_cost > 0:
                    change = round(((mtd_cost - prev_cost) / prev_cost) * 100, 1)

                explorer.append(
                    {
                        "project": proj_id,
                        "service": service_desc,
                        "cost": round(mtd_cost, 2),
                        "change": change,
                    }
                )

            explorer.sort(key=lambda x: x["cost"], reverse=True)

        except Exception as e:
            logger.error(f"Error querying explorer data: {e}")

    # Construct complete payload
    return {
        "currency": currency,
        "mtdSpend": mtd_spend,
        "mtdChange": mtd_change,
        "forecast": forecast,
        "forecastLabel": "Projected end-of-month",
        "anomaliesCount": anomalies_count,
        "zombieWaste": zombie_waste,
        "recentSpikes": recent_spikes,
        "topServices": top_services,
        "zombies": zombies,
        "explorer": explorer,
    }
