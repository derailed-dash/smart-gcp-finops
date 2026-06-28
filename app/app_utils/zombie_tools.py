"""
Description: Zombie resources custom tools.
Why: Exposes cached zombie asset list queries to both the FastAPI BFF and the ADK agent.
How: Scans projects using CAI, checks unattached resources (disks/IPs), calculates potential savings, and applies cache logic.
"""

import logging
import threading
import time

from google.adk.tools import ToolContext
from google.cloud import bigquery

from app.app_utils.credentials import get_credentials
from app.app_utils.project_discovery import get_projects_in_org, list_billing_projects
from app.app_utils.query_cache import execute_cached_query
from app.app_utils.zombie_resources import search_zombie_resources
from app.config import settings

logger = logging.getLogger(__name__)

# Global thread-safe cache for zombie resources category search
# Format: {(category, project_id): (expiry_timestamp, list_of_zombies)}
_ZOMBIE_CACHE: dict[tuple[str, str | None], tuple[float, list[dict]]] = {}
_ZOMBIE_LOCK = threading.Lock()
ZOMBIE_CACHE_TTL = 300  # 5 minutes


def get_active_billing_projects() -> list[str]:
    """Retrieves all project IDs that have had cost > 0 in the last 30 days from BigQuery."""
    try:
        credentials = get_credentials()
        client = bigquery.Client(
            credentials=credentials, project=settings.google_cloud_billing_project
        )

        billing_suffix = settings.google_cloud_billing_account.replace("-", "_")
        standard_table_id = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_v1_{billing_suffix}"

        query = f"""
        SELECT project.id
        FROM `{standard_table_id}`
        WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
          AND project.id IS NOT NULL
        GROUP BY project.id
        HAVING SUM(cost) > 0.1
        """
        results = execute_cached_query(client, query)
        return [row.id for row in results if row.id]
    except Exception as e:
        logger.warning(
            f"Failed to query active projects from BigQuery, falling back to all projects: {e}"
        )
        return []


def list_zombie_resources(
    category: str,
    project_id: str | None = None,
    tool_context: ToolContext | None = None,
) -> list[dict]:
    """Searches for zombie resources in your billing footprint (optionally filtered by a specific project ID).

    This tool is thread-safe and cached for 5 minutes to avoid slow and expensive
    Asset Inventory scans on successive steps or turns.

    Args:
        category: The category of zombie resources to find. Must be 'UNATTACHED_DISKS' or 'IDLE_IPS'.
        project_id: Optional project ID to limit the scan to a specific project.
        tool_context: ADK ToolContext (optional).

    Returns:
        list[dict]: A list of dictionary objects representing the zombie resources found.
    """
    now = time.time()
    cache_key = (category, project_id)

    # 1. Thread-safe cache check
    with _ZOMBIE_LOCK:
        if cache_key in _ZOMBIE_CACHE:
            expiry, cached_data = _ZOMBIE_CACHE[cache_key]
            if now <= expiry:
                logger.info(
                    f"Cache hit for zombie resource search: {category} (project: {project_id})"
                )
                return cached_data

    logger.info(
        f"Cache miss for zombie resource search: {category} (project: {project_id}). Scanning assets..."
    )

    # If project_id is specified, scan ONLY that project scope directly
    if project_id:
        scope = f"projects/{project_id}"
        results_list = search_zombie_resources(scope=scope, category=category)
        with _ZOMBIE_LOCK:
            _ZOMBIE_CACHE[cache_key] = (now + ZOMBIE_CACHE_TTL, results_list)
        return results_list

    # Otherwise, proceed with organization-wide / billing footprint sweep
    billing_account_name = f"billingAccounts/{settings.google_cloud_billing_account}"

    all_zombies_map = {}
    projects_in_org = set()

    # 1. Organization Scope: The most efficient global search
    if settings.google_cloud_organization:
        scope = f"organizations/{settings.google_cloud_organization}"
        for asset in search_zombie_resources(scope=scope, category=category):
            all_zombies_map[asset["name"]] = asset

        # Identify projects within the organization to avoid redundant individual queries
        projects_in_org = get_projects_in_org(settings.google_cloud_organization)

    # 2. Project Scope: Fallback/Supplement for projects outside the Org
    # Query only projects that actually have recorded costs (cost > 0.1) in BigQuery
    billing_projects = get_active_billing_projects()
    if not billing_projects:
        # Fall back to listing all billing projects if BigQuery is empty or failed
        billing_projects = list_billing_projects(billing_account_name)

    # Only query projects that were not covered by the organization search
    projects_to_query = [p for p in billing_projects if p not in projects_in_org]

    from concurrent.futures import ThreadPoolExecutor

    def scan_project(p_id: str):
        scope = f"projects/{p_id}"
        return search_zombie_resources(scope=scope, category=category)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(scan_project, p): p for p in projects_to_query}
        for future in futures:
            try:
                assets = future.result()
                for asset in assets:
                    all_zombies_map[asset["name"]] = asset
            except Exception as e:
                logger.error(
                    f"Error scanning project {futures[future]} for zombies: {e}"
                )

    results_list = list(all_zombies_map.values())

    # Store results in the thread-safe cache
    with _ZOMBIE_LOCK:
        _ZOMBIE_CACHE[cache_key] = (now + ZOMBIE_CACHE_TTL, results_list)

    return results_list


def clear_zombie_cache() -> None:
    """Clears all cached zombie resources. Useful for testing."""
    with _ZOMBIE_LOCK:
        _ZOMBIE_CACHE.clear()
