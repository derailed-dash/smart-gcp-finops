"""Cloud Asset Inventory search queries for idle and orphaned ('zombie') GCP resources.

What:
    Queries Google Cloud Asset Inventory (CAI) for unused, unattached, or idle infrastructure resources
    (such as unattached Compute Engine disks and idle reserved IP addresses).

Why:
    Identifies immediate cost optimization opportunities by surfacing wasted assets across configured project scopes.

How:
    Executes CAI ``searchAllResources`` queries using predefined resource filter configurations and uses CAI REST
    clients to return raw asset dictionaries.
"""

import logging

from finops_agent.app_utils.cai_utils import get_service

logger = logging.getLogger(__name__)

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
    """Searches for zombie resources in the given scope.

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
