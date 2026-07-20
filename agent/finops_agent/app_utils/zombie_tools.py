"""
Description: Zombie resources custom tools.
Why: Exposes cached zombie asset list queries to both the FastAPI BFF and the ADK agent.
How: Scans projects using CAI, checks unattached resources (disks/IPs), calculates potential savings, and applies cache logic.
"""

import logging
import re
import threading
import time

from google.adk.tools import ToolContext
from google.cloud import bigquery

from finops_agent.app_utils.credentials import get_credentials
from finops_agent.app_utils.project_discovery import (
    get_projects_in_org,
    list_billing_projects,
)
from finops_agent.app_utils.zombie_resources import search_zombie_resources
from finops_agent.config import settings

logger = logging.getLogger(__name__)

# Global thread-safe cache for zombie resources category search
# Format: {(category, project_id): (expiry_timestamp, list_of_zombies)}
_ZOMBIE_CACHE: dict[tuple[str, str | None], tuple[float, list[dict]]] = {}
_ZOMBIE_LOCK = threading.Lock()
ZOMBIE_CACHE_TTL = 300  # 5 minutes


def get_active_billing_projects(tool_context: ToolContext | None = None) -> list[str]:
    """Retrieves all project IDs that have had cost > 0 in the last 30 days from BigQuery."""
    from unittest.mock import MagicMock
    if tool_context and tool_context.state and not isinstance(tool_context.state, MagicMock):
        if "active_billing_projects" in tool_context.state:
            logger.debug("Active billing projects cache hit in session state.")
            return tool_context.state["active_billing_projects"]

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
        job = client.query(query)
        results = list(job.result())
        projects = [row.id for row in results if row.id]

        if tool_context and tool_context.state and not isinstance(tool_context.state, MagicMock):
            tool_context.state["active_billing_projects"] = projects

        return projects
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

    # 1. ADK session state cache check (survives container scale-down)
    if tool_context and tool_context.state:
        state_key = f"zombies_{category}_{project_id}"
        if state_key in tool_context.state:
            expiry, cached_data = tool_context.state[state_key]
            if now <= expiry:
                logger.debug(
                    f"Session state cache hit for zombie resource: {category} (project: {project_id})"
                )
                return cached_data

    # 2. Thread-safe global cache check
    with _ZOMBIE_LOCK:
        if cache_key in _ZOMBIE_CACHE:
            expiry, cached_data = _ZOMBIE_CACHE[cache_key]
            if now <= expiry:
                logger.debug(
                    f"Global cache hit for zombie resource search: {category} (project: {project_id})"
                )
                # Sync back to session state for subsequent turns
                if tool_context and tool_context.state:
                    state_key = f"zombies_{category}_{project_id}"
                    tool_context.state[state_key] = (expiry, cached_data)
                return cached_data

    logger.debug(
        f"Cache miss for zombie resource search: {category} (project: {project_id}). Scanning assets..."
    )

    # Resolve allowed projects for security scoping
    allowed_projects = None
    if tool_context and tool_context.state:
        allowed_projects = tool_context.state.get("allowed_projects")

    # Fallback to discovering projects if missing from state
    if allowed_projects is None and tool_context and tool_context.user_id:
        from finops_agent.app_utils.project_discovery import (
            get_user_accessible_projects,
        )

        allowed_projects = list(get_user_accessible_projects(tool_context.user_id))
        tool_context.state["allowed_projects"] = allowed_projects

    # If project_id is specified, verify user has access to it
    if project_id:
        if allowed_projects is not None and project_id not in allowed_projects:
            logger.warning(f"Unauthorized check: user does not have access to project {project_id}")
            return [{"error": f"Unauthorized. You do not have access to project '{project_id}'."}]

        scope = f"projects/{project_id}"
        results_list = search_zombie_resources(scope=scope, category=category)
        with _ZOMBIE_LOCK:
            _ZOMBIE_CACHE[cache_key] = (now + ZOMBIE_CACHE_TTL, results_list)
        if tool_context and tool_context.state:
            state_key = f"zombies_{category}_{project_id}"
            tool_context.state[state_key] = (now + ZOMBIE_CACHE_TTL, results_list)
        return results_list

    # Otherwise, scan all allowed projects
    if allowed_projects is not None and not allowed_projects:
        logger.warning("Unauthorized check: user has access to 0 projects.")
        return []

    all_zombies_map = {}
    projects_in_org = set()

    # 1. Organization Scope: Efficient global search (if organization is configured)
    if settings.google_cloud_organization:
        scope = f"organizations/{settings.google_cloud_organization}"
        for asset in search_zombie_resources(scope=scope, category=category):
            # Parse project ID from resource name (e.g. //compute.googleapis.com/projects/PROJECT_ID/...)
            project_match = re.search(r"/projects/([^/]+)", asset.get("name", ""))
            asset_project = project_match.group(1) if project_match else None
            # Security filter: ensure asset belongs to allowed projects
            if allowed_projects is None or (asset_project and asset_project in allowed_projects):
                all_zombies_map[asset["name"]] = asset

        projects_in_org = get_projects_in_org(settings.google_cloud_organization)

    # 2. Project Scope fallback/scan for projects not covered by org search
    # If allowed_projects list is available, use that as the base project list to scan
    if allowed_projects is not None:
        projects_to_query = [p for p in allowed_projects if p not in projects_in_org]
    else:
        billing_account_name = f"billingAccounts/{settings.google_cloud_billing_account}"
        billing_projects = get_active_billing_projects(tool_context)
        if not billing_projects:
            billing_projects = list_billing_projects(billing_account_name)
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
                logger.error(f"Error scanning project {futures[future]} for zombies: {e}")

    results_list = list(all_zombies_map.values())

    with _ZOMBIE_LOCK:
        _ZOMBIE_CACHE[cache_key] = (now + ZOMBIE_CACHE_TTL, results_list)

    if tool_context and tool_context.state:
        state_key = f"zombies_{category}_{project_id}"
        tool_context.state[state_key] = (now + ZOMBIE_CACHE_TTL, results_list)

    return results_list


def clear_zombie_cache() -> None:
    """Clears all cached zombie resources. Useful for testing."""
    with _ZOMBIE_LOCK:
        _ZOMBIE_CACHE.clear()
