"""
Description: Dashboard metrics and telemetry compiler.
Why: Calculates aggregated cost data, forecasting curves, anomaly lists, and zombie assets for the React UI.
How: Executes optimized BigQuery SQL queries, applies user project security scoping filters, and merges Cloud Asset Inventory data.
"""

import calendar
import logging
import re
import statistics
from datetime import datetime, timedelta

from google.auth import default
from google.cloud import bigquery

from finops_agent.app_utils.query_cache import execute_cached_query
from finops_agent.app_utils.zombie_tools import list_zombie_resources
from finops_agent.config import settings

# Inherits effective log level from the root logger
# configured in fast_api_app.py / agent_runtime_app.py
logger = logging.getLogger(__name__)


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
        WHERE usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
        {project_filter}
        LIMIT 1
        """
        cur_results = execute_cached_query(client, currency_query)
        if cur_results:
            currency = cur_results[0].currency or "GBP"
    except Exception as e:
        logger.error(f"Error querying dynamic currency: {e}")

    # 2. Query Month-to-Date Spend and MoM Change
    now = datetime.now()
    current_year_month = now.strftime("%Y-%m")

    # We will get monthly costs for the last two calendar months
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

    mtd_spend = 0.0
    mtd_change = 0.0
    forecast = 0.0

    try:
        month_results = execute_cached_query(client, month_query)

        costs = {
            row.billing_month: float(row.monthly_cost or 0.0)
            for row in month_results
            if row.billing_month
        }

        # MTD Spend is the cost of the current calendar month
        mtd_spend = costs.get(current_year_month, 0.0)

        # Determine previous month key
        prev_month = now.replace(day=1) - timedelta(days=1)
        prev_year_month = prev_month.strftime("%Y-%m")
        prev_mtd_spend = costs.get(prev_year_month, 0.0)

        if prev_mtd_spend > 0:
            mtd_change = round(((mtd_spend - prev_mtd_spend) / prev_mtd_spend) * 100, 1)

        # Calculate forecast based on simple linear projection
        days_in_month = (
            client_month_days
            if client_month_days is not None
            else calendar.monthrange(now.year, now.month)[1]
        )

        # Determine elapsed days. Prefer the user's browser client day if available to prevent
        # container clock offsets. Fall back to standard container/telemetry days.
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
                day_results = execute_cached_query(client, telemetry_day_query)
                if day_results and day_results[0].max_day is not None:
                    elapsed_days = max(int(day_results[0].max_day), 1)
                    # Keep within bounds of the month's days
                    elapsed_days = min(elapsed_days, days_in_month)
            except Exception as e:
                logger.error(f"Error querying telemetry elapsed days for forecast: {e}")

        forecast = round((mtd_spend / elapsed_days) * days_in_month, 2)

        mtd_spend = round(mtd_spend, 2)
    except Exception as e:
        logger.error(f"Error querying monthly costs: {e}")

    # 3. Query Daily Costs for the last 14 days grouped by service description
    daily_query = f"""
    SELECT
      DATE(usage_start_time) as usage_date,
      service.description as service_description,
      SUM(cost) as daily_cost
    FROM `{standard_table_id}`
    WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
    {project_filter}
    GROUP BY 1, 2
    HAVING daily_cost > 0.01
    ORDER BY usage_date ASC
    """

    recent_spikes = []
    top_services = []
    anomalies_count = 0

    try:
        daily_results = execute_cached_query(client, daily_query)

        # First, aggregate total cost per service to find the top ones
        service_totals = {}
        for row in daily_results:
            srv = row.service_description or "Unknown Service"
            cost = float(row.daily_cost)
            service_totals[srv] = service_totals.get(srv, 0.0) + cost

        # Sort services by total cost descending and pick the top 3
        sorted_services = sorted(service_totals.items(), key=lambda x: x[1], reverse=True)
        top_n_services = [name for name, total in sorted_services[:3] if total > 0]

        # Group data by date
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

        # Fill the timeline sequentially
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

        # 4. Statistical Anomaly Detection
        # Calculate daily total costs to run statistical mean + std_dev checks
        daily_totals = []
        for r in recent_spikes:
            total = sum(r[k] for k in r if k != "date")
            daily_totals.append(total)

        if len(daily_totals) >= 5:
            # Clean baseline by filtering out extremely low start-up/idle days (less than 25% of median)
            median_val = statistics.median(daily_totals[:-1])
            baseline_days = [val for val in daily_totals[:-1] if val >= median_val * 0.25]
            if len(baseline_days) >= 3:
                mean = statistics.mean(baseline_days)
                std_dev = statistics.stdev(baseline_days)
            else:
                mean = statistics.mean(daily_totals[:-1])
                std_dev = statistics.stdev(daily_totals[:-1])

            # Use 1.2 * std_dev for sensitive, small-sample standard anomaly detection
            threshold = mean + 1.2 * std_dev if std_dev > 0 else mean * 1.15

            # Count days that exceed the threshold
            for total in daily_totals:
                if total > threshold:
                    anomalies_count += 1

    except Exception as e:
        logger.error(f"Error querying daily costs or detecting anomalies: {e}")

    # 5. Fetch actual zombie resources using Cloud Asset Inventory
    zombies = []
    zombie_waste = 0.0

    try:
        # Scan for unattached persistent disks
        unattached_disks = list_zombie_resources("UNATTACHED_DISKS")
        for item in unattached_disks:
            proj = item.get("project", "").split("/")[-1] if item.get("project") else "unknown"
            # Scoping Filter
            if allowed_projects is not None and proj not in allowed_projects:
                continue

            cost = estimate_zombie_cost(item, "UNATTACHED_DISKS")
            zombie_waste += cost

            # Format to structure expected by React
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

        # Scan for idle IP addresses
        idle_ips = list_zombie_resources("IDLE_IPS")
        for item in idle_ips:
            proj = item.get("project", "").split("/")[-1] if item.get("project") else "unknown"
            # Scoping Filter
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

    # 6. Query MTD spend by project & service for the Cost Explorer tab, including MoM change
    explorer = []
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
    try:
        explorer_results = execute_cached_query(client, explorer_query)

        # Group by (project_id, service_desc) -> {month: cost}
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

        # Parse months
        now = datetime.now()
        current_year_month = now.strftime("%Y-%m")
        prev_month = now.replace(day=1) - timedelta(days=1)
        prev_year_month = prev_month.strftime("%Y-%m")

        # Build explorer list based on MTD costs
        for (proj_id, service_desc), months_costs in explorer_data_map.items():
            mtd_cost = months_costs.get(current_year_month, 0.0)
            # If there is no cost in the current month, skip it to focus on active MTD spend
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

        # Sort explorer rows by cost descending
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
