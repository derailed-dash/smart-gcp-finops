"""
Description: Utility for discovering projects linked to a billing account.
Why: Enables the agent to understand the full infrastructure footprint.
How: Uses the Cloud Billing API to list projects associated with a billing account.
"""

import logging

from app.app_utils.cai_utils import get_service

logger = logging.getLogger(__name__)


def list_billing_projects(billing_account_name: str) -> list[str]:
    """
    Lists all projects associated with a given billing account.

    Args:
        billing_account_name: The resource name of the billing account,
            e.g., 'billingAccounts/012345-ABCDEF-012345'.

    Returns:
        A list of project IDs.
    """
    try:
        service = get_service("cloudbilling", "v1")

        request = service.billingAccounts().projects().list(name=billing_account_name)
        projects = []

        while request is not None:
            response = request.execute()

            project_billing_info = response.get("projectBillingInfo", [])
            for info in project_billing_info:
                projects.append(info["projectId"])

            request = (
                service.billingAccounts()
                .projects()
                .list_next(previous_request=request, previous_response=response)
            )

        return projects

    except Exception as e:
        logger.error(
            f"Error listing projects for billing account {billing_account_name}: {e}"
        )
        return []


def get_projects_in_org(org_id: str) -> set[str]:
    """
    Retrieves all project IDs within a given organization using Cloud Asset Inventory.

    Args:
        org_id: The Google Cloud Organization ID.

    Returns:
        A set of project IDs.
    """
    try:
        service = get_service("cloudasset", "v1")
        scope = f"organizations/{org_id}"
        asset_types = ["cloudresourcemanager.googleapis.com/Project"]

        projects = set()
        request = service.v1().searchAllResources(scope=scope, assetTypes=asset_types)

        while request is not None:
            response = request.execute()
            for asset in response.get("results", []):
                # The resource name format is //cloudresourcemanager.googleapis.com/projects/PROJECT_ID
                name = asset.get("name", "")
                if "/projects/" in name:
                    project_id = name.split("/projects/")[-1]
                    projects.add(project_id)

            request = service.v1().searchAllResources_next(
                previous_request=request, previous_response=response
            )

        return projects
    except Exception as e:
        logger.warning(f"Failed to list projects in organization {org_id}: {e}")
        return set()
