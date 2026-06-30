"""
Description: Cloud Asset Inventory (CAI) custom tools.
Why: Exposes project, resource, and history scanning capabilities to the agent.
How: Integrates with CAI REST APIs using the Google API Python client,
providing cached discovery and temporal configuration drift checks.
"""

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial

from google.adk.tools import ToolContext

from app.app_utils.cai_utils import (
    enrich_with_cai_metadata,
    get_asset_history,
    is_org_scope_disabled,
)
from app.app_utils.project_discovery import list_billing_projects
from app.config import settings

# Inherits effective log level from the root logger
# configured in fast_api_app.py / agent_runtime_app.py
logger = logging.getLogger(__name__)

# Thread-safe in-memory cache for CAI metadata
# Format: {sorted_tuple_of_resource_names: (expiry_timestamp, list_of_metadata)}
_METADATA_CACHE: dict[tuple[str, ...], tuple[float, list[dict]]] = {}
_METADATA_CACHE_LOCK = threading.Lock()

# Thread-safe in-memory cache for CAI resource history
# Format: {(resource_name, start_time, end_time): (expiry_timestamp, list_of_history)}
_HISTORY_CACHE: dict[tuple[str, str, str | None], tuple[float, list[dict]]] = {}
_HISTORY_CACHE_LOCK = threading.Lock()

CAI_CACHE_TTL = 300  # 5 minutes


def get_cai_metadata_for_resources(
    resource_names: list[str], tool_context: ToolContext | None = None
) -> list[dict]:
    """Retrieves Cloud Asset Inventory (CAI) metadata for a specific list of resource names.

    Use this tool when you have identified resource names (e.g., from BigQuery billing data)
    and need to cross-reference them with their current operational state in CAI.

    Args:
        resource_names: A list of full resource URIs (e.g., '//compute.googleapis.com/projects/p1/zones/z1/disks/d1').
        tool_context: ADK ToolContext (optional).

    Returns:
        list[dict]: A list of CAI asset metadata objects for the requested resources.
    """
    if not resource_names:
        return []

    # Sort to ensure cache key consistency
    cache_key = tuple(sorted(resource_names))
    now = time.time()
    with _METADATA_CACHE_LOCK:
        if cache_key in _METADATA_CACHE:
            expiry, cached_data = _METADATA_CACHE[cache_key]
            if now <= expiry:
                return cached_data

    all_metadata = []

    # 1. Organization Scope: The most efficient global search
    names_to_query = set(resource_names)
    if settings.google_cloud_organization and not is_org_scope_disabled():
        scope = f"organizations/{settings.google_cloud_organization}"
        cost_records_mock = [{"resource_name": name} for name in names_to_query]
        enriched = enrich_with_cai_metadata(cost_records_mock, scope)
        for record in enriched:
            if record.get("cai_metadata"):
                all_metadata.append(record["cai_metadata"])
                if record["resource_name"] in names_to_query:
                    names_to_query.remove(record["resource_name"])

    if not names_to_query:
        return all_metadata

    # 2. Resource Grouping (Project Scope Fallback)
    resources_by_scope = {}
    unmatched_names = []

    for name in names_to_query:
        match = re.search(r"/projects/([^/]+)", name)
        if match:
            scope = f"projects/{match.group(1)}"
            resources_by_scope.setdefault(scope, []).append(name)
        else:
            unmatched_names.append(name)

    for scope, names in resources_by_scope.items():
        records = [{"resource_name": n} for n in names]
        enriched = enrich_with_cai_metadata(records, scope)
        for record in enriched:
            if record.get("cai_metadata"):
                all_metadata.append(record["cai_metadata"])

    # 3. Last Resort Fallback: If URIs lacked project IDs
    if unmatched_names:
        billing_account_name = (
            f"billingAccounts/{settings.google_cloud_billing_account}"
        )
        project_ids = list_billing_projects(billing_account_name)
        unmatched_records = [{"resource_name": name} for name in unmatched_names]

        # Use a partial function to curry the fixed 'unmatched_records' argument
        enrich_func = partial(enrich_with_cai_metadata, unmatched_records)

        with ThreadPoolExecutor() as executor:
            # Map the enrich function over the project scopes that need checking
            scopes_to_check = [
                f"projects/{pid}"
                for pid in project_ids
                if f"projects/{pid}" not in resources_by_scope
            ]
            results = executor.map(enrich_func, scopes_to_check)

            for enriched_chunk in results:
                for record in enriched_chunk:
                    if (
                        record.get("cai_metadata")
                        and record["cai_metadata"] not in all_metadata
                    ):
                        all_metadata.append(record["cai_metadata"])

    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE[cache_key] = (now + CAI_CACHE_TTL, all_metadata)

    return all_metadata


def get_cai_history_for_resource(
    resource_name: str,
    start_time: str,
    end_time: str | None = None,
    tool_context: ToolContext | None = None,
) -> list[dict]:
    """Retrieves the configuration history for a specific resource.

    Use this tool when investigating a cost spike for a specific resource to determine
    if its configuration changed (e.g., machine type was upgraded) during the 35-day CAI history window.
    CAI only retains history for 35 days. If start_time is older than 35 days from now, it will be automatically adjusted to 35 days ago to prevent API errors.

    Args:
        resource_name: The full CAI name of the resource (e.g., '//compute.googleapis.com/projects/p1/zones/z1/instances/i1').
        start_time: ISO 8601 timestamp for the start of the time window (e.g., '2026-03-01T00:00:00Z').
        end_time: ISO 8601 timestamp for the end of the time window (optional).
        tool_context: ADK ToolContext (optional).

    Returns:
        list[dict]: A list of historical asset states showing configuration changes over time.
    """

    # Enforce CAI 35-day history limit
    try:
        # Standardize the timestamp format to match what Google API expects (RFC 3339)
        # ADK/LLMs sometimes output "Z" which Google's Python client doesn't always parse cleanly
        # or they omit the +00:00 timezone indicator entirely.
        if "Z" in start_time:
            start_time = start_time.replace("Z", "+00:00")
        elif "+" not in start_time and "-" not in start_time.split("T")[-1]:
            start_time = f"{start_time}+00:00"

        start_dt = datetime.fromisoformat(start_time)
        min_allowed_dt = datetime.now(UTC) - timedelta(
            days=34, hours=23, minutes=50
        )  # Slightly less than 35 days to be safe

        if start_dt < min_allowed_dt:
            # Adjust to the minimum allowed time to prevent 400 Bad Request
            start_time = min_allowed_dt.isoformat()
    except Exception:
        pass  # If parsing fails, pass it through to the API to handle

    # Ensure end_time is also properly formatted if provided
    if end_time:
        try:
            if "Z" in end_time:
                end_time = end_time.replace("Z", "+00:00")
            elif "+" not in end_time and "-" not in end_time.split("T")[-1]:
                end_time = f"{end_time}+00:00"
        except Exception:
            pass

    logger.debug(
        "Requesting CAI history: resource_name=%s, start_time=%s, end_time=%s",
        resource_name,
        start_time,
        end_time,
    )

    cache_key = (resource_name, start_time, end_time)
    now = time.time()
    with _HISTORY_CACHE_LOCK:
        if cache_key in _HISTORY_CACHE:
            expiry, cached_data = _HISTORY_CACHE[cache_key]
            if now <= expiry:
                logger.debug(
                    "CAI history cache hit for resource: %s (returned %d records)",
                    resource_name,
                    len(cached_data),
                )
                return cached_data

    history_results = []

    # 1. Try project-level lookup first if project can be extracted from resource name
    project_match = re.search(r"/projects/([^/]+)", resource_name)
    if project_match:
        scope = f"projects/{project_match.group(1)}"
        history_results = get_asset_history(resource_name, scope, start_time, end_time)

    # 2. Fall back to organization scope if no history was found (or project wasn't extracted)
    # AND organization scope has not been disabled due to 403 errors
    if (
        not history_results
        and settings.google_cloud_organization
        and not is_org_scope_disabled()
    ):
        scope = f"organizations/{settings.google_cloud_organization}"
        history_results = get_asset_history(resource_name, scope, start_time, end_time)

    # 3. Fallback to querying all billing projects if previous steps yielded nothing
    if not history_results:
        billing_account_name = (
            f"billingAccounts/{settings.google_cloud_billing_account}"
        )
        project_ids = list_billing_projects(billing_account_name)

        # Avoid re-querying the project we already queried in step 1
        queried_projects = {project_match.group(1)} if project_match else set()
        for project_id in project_ids:
            if project_id in queried_projects:
                continue
            scope = f"projects/{project_id}"
            history_results = get_asset_history(
                resource_name, scope, start_time, end_time
            )
            if history_results:
                break

    logger.debug(
        "CAI history lookup returned %d records for resource: %s",
        len(history_results),
        resource_name,
    )

    with _HISTORY_CACHE_LOCK:
        _HISTORY_CACHE[cache_key] = (now + CAI_CACHE_TTL, history_results)

    return history_results


def clear_cai_caches() -> None:
    """Clears all cached CAI metadata and history results. Useful for testing."""
    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE.clear()
    with _HISTORY_CACHE_LOCK:
        _HISTORY_CACHE.clear()
