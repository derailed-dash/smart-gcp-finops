"""
Description: Cloud Asset Inventory (CAI) utility functions.
Why: Provides low-level connection managers and client setup helpers for CAI API requests.
How: Sets up thread-local API discovery clients to ensure thread-safe resource queries
and handles fallback scope detections.
"""

import logging
import threading
from typing import Any

from googleapiclient import discovery
from googleapiclient.errors import HttpError

from app.app_utils.credentials import get_credentials

logger = logging.getLogger(__name__)


class CAIClientManager:
    """Manages thread-safe discovery services and global state for Cloud Asset Inventory."""

    def __init__(self) -> None:
        self._thread_local = threading.local()
        self.org_scope_disabled = False
        self._org_scope_lock = threading.Lock()

    def is_org_scope_disabled(self) -> bool:
        """Returns True if the organization scope has been disabled due to permission errors."""
        with self._org_scope_lock:
            return self.org_scope_disabled

    def disable_org_scope(self) -> None:
        """Disables the organization scope because a 403 error was encountered."""
        with self._org_scope_lock:
            if not self.org_scope_disabled:
                self.org_scope_disabled = True
                logger.info(
                    "Cloud Asset Inventory organization scope has been disabled due to permission errors (403)."
                )

    def get_service(self, service_name: str, version: str) -> Any:
        """Returns a cached thread-safe discovery service instance, building it if necessary."""
        if not hasattr(self._thread_local, "services"):
            self._thread_local.services = {}

        cache_key = f"{service_name}_{version}"
        if cache_key not in self._thread_local.services:
            credentials = get_credentials()
            self._thread_local.services[cache_key] = discovery.build(
                service_name, version, credentials=credentials, cache_discovery=False
            )
        return self._thread_local.services[cache_key]

    def reset(self) -> None:
        """Clears the internal services cache and resets scope settings. Primarily used for testing."""
        if hasattr(self._thread_local, "services"):
            self._thread_local.services = {}
        with self._org_scope_lock:
            self.org_scope_disabled = False

    def enrich_with_cai_metadata(self, cost_records: list[dict], scope: str) -> list[dict]:
        """
        Enriches cost records with CAI metadata by looking up the resource_name in CAI.

        Args:
            cost_records: List of dictionaries representing cost records. Must contain a 'resource_name' key.
            scope: The search scope (e.g., 'projects/test-project' or 'organizations/123').

        Returns:
            The enriched list of cost records.
        """
        if not cost_records:
            return cost_records

        # Extract unique resource names from the cost records
        all_resource_names = list(
            {
                record.get("resource_name")
                for record in cost_records
                if record.get("resource_name")
            }
        )

        if not all_resource_names:
            return cost_records

        cai_metadata_map = {}
        service = self.get_service("cloudasset", "v1")
        CHUNK_SIZE = 20

        for i in range(0, len(all_resource_names), CHUNK_SIZE):
            chunk = all_resource_names[i : i + CHUNK_SIZE]
            query_parts = [f'name="{name}"' for name in chunk]
            query = " OR ".join(query_parts)

            try:
                request = service.v1().searchAllResources(scope=scope, query=query)
                while request is not None:
                    response = request.execute()
                    for asset in response.get("results", []):
                        cai_metadata_map[asset["name"]] = asset

                    request = service.v1().searchAllResources_next(
                        previous_request=request, previous_response=response
                    )
            except HttpError as e:
                if e.resp.status == 403:
                    logger.warning(
                        f"Permission denied for CAI metadata search in scope {scope}. "
                        "If this is an organization scope, ensure the service account has 'roles/cloudasset.viewer' at the organization level."
                    )
                    if scope.startswith("organizations/"):
                        self.disable_org_scope()
                else:
                    logger.error(
                        f"HTTP error during CAI metadata chunk search in scope {scope}: {e}"
                    )
            except Exception as e:
                logger.error(
                    f"Unexpected error during CAI metadata chunk search in scope {scope}: {e}"
                )

        # Enrich the original records
        enriched_records = []
        for record in cost_records:
            enriched_record = record.copy()
            resource_name = record.get("resource_name")
            if resource_name and resource_name in cai_metadata_map:
                enriched_record["cai_metadata"] = cai_metadata_map[resource_name]
            enriched_records.append(enriched_record)

        return enriched_records

    def get_asset_history(
        self, resource_name: str, scope: str, start_time: str, end_time: str | None = None
    ) -> list[dict]:
        """
        Retrieves the historical changes for a specific CAI resource.

        Args:
            resource_name: The full CAI name of the resource.
            scope: The search scope (e.g., 'projects/test-project').
            start_time: ISO 8601 timestamp for the start of the time window.
            end_time: Optional ISO 8601 timestamp for the end of the time window.

        Returns:
            A list of historical asset states.
        """
        try:
            service = self.get_service("cloudasset", "v1")

            request = service.v1().batchGetAssetsHistory(
                parent=scope,
                assetNames=[resource_name],
                contentType="RESOURCE",
                readTimeWindow_startTime=start_time,
                readTimeWindow_endTime=end_time,
            )

            response = request.execute()
            return response.get("assets", [])

        except HttpError as e:
            if e.resp.status == 403:
                logger.warning(
                    f"Permission denied for CAI history lookup for {resource_name} in scope {scope}. "
                    "The system will attempt to fallback to project-level lookups if possible."
                )
                if scope.startswith("organizations/"):
                    self.disable_org_scope()
            else:
                logger.error(
                    f"HTTP error querying CAI history for {resource_name} in scope {scope}: {e}"
                )
            return []
        except Exception as e:
            logger.error(
                f"Unexpected error querying CAI history for {resource_name} in scope {scope}: {e}"
            )
            return []


# Module-level singleton instance for shared client management
cai_client_manager = CAIClientManager()


def is_org_scope_disabled() -> bool:
    """Returns True if the organization scope has been disabled due to permission errors."""
    return cai_client_manager.is_org_scope_disabled()


def disable_org_scope() -> None:
    """Disables the organization scope because a 403 error was encountered."""
    cai_client_manager.disable_org_scope()


def get_service(service_name: str, version: str) -> Any:
    """Returns a cached thread-safe discovery service instance, building it if necessary."""
    return cai_client_manager.get_service(service_name, version)


def clear_services_cache() -> None:
    """Clears the internal services cache. Primarily used for unit testing."""
    cai_client_manager.reset()


def enrich_with_cai_metadata(cost_records: list[dict], scope: str) -> list[dict]:
    """Enriches cost records with CAI metadata by looking up the resource_name in CAI."""
    return cai_client_manager.enrich_with_cai_metadata(cost_records, scope)


def get_asset_history(
    resource_name: str, scope: str, start_time: str, end_time: str | None = None
) -> list[dict]:
    """Retrieves the historical changes for a specific CAI resource."""
    return cai_client_manager.get_asset_history(resource_name, scope, start_time, end_time)

