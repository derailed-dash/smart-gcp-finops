"""
Description: Utility for finding 'zombie' resources using Cloud Asset Inventory.
Why: Helps identify cost waste such as unattached disks or idle IPs.
How: Uses the Cloud Asset API's searchAllResources method.
"""

import logging

from app.app_utils.cai_utils import get_service

# Inherits effective log level from the root logger
# configured in fast_api_app.py / agent_runtime_app.py
logger = logging.getLogger(__name__)

# CAI searchAllResources supports filtering by assetTypes via a separate parameter.
# The `users` field is not supported in searchAllResources query for these types in CAI API directly.
# We will query for the state and then filter the results programmatically if needed.
QUERIES = {
    "UNATTACHED_DISKS": {
        "assetTypes": ["compute.googleapis.com/Disk"],
        "query": "state=READY",
    },
    "IDLE_IPS": {
        "assetTypes": ["compute.googleapis.com/Address"],
        "query": "state=RESERVED",
    },
}


def search_zombie_resources(scope: str, category: str) -> list[dict]:
    """
    Searches for zombie resources in the given scope.

    Args:
        scope: The scope of the search, e.g., 'projects/12345', 'folders/123', 'organizations/123'.
        category: The category of zombie resources ('UNATTACHED_DISKS', 'IDLE_IPS').

    Returns:
        A list of asset dictionaries.
    """
    if category not in QUERIES:
        logger.error(f"Unknown zombie resource category: {category}")
        return []

    query_info = QUERIES[category]

    try:
        service = get_service("cloudasset", "v1")

        logger.debug(
            "Searching zombie resources: scope=%s, category=%s, query=%s, assetTypes=%s",
            scope,
            category,
            query_info["query"],
            query_info["assetTypes"],
        )
        request = service.v1().searchAllResources(
            scope=scope, query=query_info["query"], assetTypes=query_info["assetTypes"]
        )
        assets = []

        while request is not None:
            response = request.execute()
            raw_results = response.get("results", [])
            logger.debug("Raw searchAllResources returned %d asset results.", len(raw_results))

            # CAI doesn't support the `-users:*` query directly for all resource types.
            # We fetch READY disks / RESERVED IPs and then filter out those that have 'users'
            for item in raw_results:
                # Only append if 'users' is missing or empty (meaning it's unattached/idle)
                if not item.get("additionalAttributes", {}).get("users"):
                    assets.append(item)

            request = service.v1().searchAllResources_next(
                previous_request=request, previous_response=response
            )

        logger.debug("Filtered zombie assets (category=%s) count: %d", category, len(assets))
        if assets:
            logger.debug("Snippet of first zombie asset: %s", assets[0])
        return assets

    except Exception as e:
        logger.error(f"Error searching zombie resources for scope {scope}: {e}")
        return []
