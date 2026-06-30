"""
Description: Utility for discovering projects linked to a billing account.
Why: Enables the agent to understand the full infrastructure footprint.
How: Uses the Cloud Billing API to list projects associated with a billing account.
"""

import logging
import threading
import time

from app.app_utils.cai_utils import get_service
from app.config import settings

# Inherits effective log level from the root logger
# configured in fast_api_app.py / agent_runtime_app.py
logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 600  # 10 minutes


class ProjectDiscoveryManager:
    """Manages thread-safe caching and lookup of user-accessible Google Cloud projects."""

    def __init__(self) -> None:
        self.user_projects_cache: dict[str, tuple[float, set[str]]] = {}
        self.cache_lock = threading.Lock()

    def get_user_accessible_projects(self, user_email: str) -> set[str]:
        """Discovers all project IDs that the given user has access to.

        Uses Cloud Asset Inventory's searchAllIamPolicies if an organization is configured,
        falling back to project-level IAM policy checks for standalone projects.
        """
        if not user_email:
            return set()

        now = time.time()

        # Read from cache if valid
        with self.cache_lock:
            if user_email in self.user_projects_cache:
                expiry, cached_projects = self.user_projects_cache[user_email]
                if now <= expiry:
                    logger.debug("Cache hit for user accessible projects: %s", user_email)
                    return cached_projects

        logger.debug("Cache miss for user accessible projects: %s. Performing lookup...", user_email)
        projects = set()
        has_top_level_access = False

        # Scenario A: Organization-level discovery using Cloud Asset Inventory
        if settings.google_cloud_organization:
            try:
                service = get_service("cloudasset", "v1")
                scope = f"organizations/{settings.google_cloud_organization}"
                query = f"policy:{user_email}"

                logger.debug("Querying searchAllIamPolicies: scope=%s, query=%s", scope, query)
                request = service.v1().searchAllIamPolicies(scope=scope, query=query)
                while request is not None:
                    response = request.execute()
                    logger.debug(
                        "searchAllIamPolicies returned %d policy bindings.",
                        len(response.get("results", [])),
                    )
                    if response.get("results"):
                        logger.debug(
                            "Snippet of first IAM policy binding match: %s",
                            response.get("results")[0],
                        )
                    for result in response.get("results", []):
                        resource = result.get("resource", "")
                        # If user has access at org or folder level, they inherit access
                        if "/organizations/" in resource or "/folders/" in resource:
                            has_top_level_access = True
                        elif "/projects/" in resource:
                            proj_id = resource.split("/projects/")[-1]
                            projects.add(proj_id)

                    request = service.v1().searchAllIamPolicies_next(
                        previous_request=request, previous_response=response
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to query Cloud Asset IAM policies for organization {settings.google_cloud_organization}: {e}. "
                    "Falling back to project-level check."
                )

        # Scenario B: Fallback to project-level check for standalone or billing projects
        if not settings.google_cloud_organization or (not projects and not has_top_level_access):
            try:
                # 1. Discover all projects linked to the billing account
                billing_account = f"billingAccounts/{settings.google_cloud_billing_account}"
                all_billing_projects = list_billing_projects(billing_account)
                logger.debug("Falling back to project-level checks. Auditing %d billing projects.", len(all_billing_projects))

                # 2. Query each project's IAM policy
                crm_service = get_service("cloudresourcemanager", "v1")
                for project_id in all_billing_projects:
                    try:
                        policy = crm_service.projects().getIamPolicy(resource=project_id).execute()
                        logger.debug(
                            "Fetched IAM policy for project %s. bindings count: %d",
                            project_id,
                            len(policy.get("bindings", [])),
                        )
                        if policy.get("bindings"):
                            logger.debug(
                                "Snippet of first policy binding: %s",
                                policy.get("bindings")[0],
                            )

                        is_member = False
                        user_domain = user_email.split("@")[-1] if "@" in user_email else ""

                        for binding in policy.get("bindings", []):
                            for member in binding.get("members", []):
                                member_lower = member.lower()
                                if (
                                    member_lower == f"user:{user_email.lower()}"
                                    or member_lower == f"group:{user_email.lower()}"
                                    or (user_domain and member_lower == f"domain:{user_domain.lower()}")
                                ):
                                    is_member = True
                                    break
                            if is_member:
                                break

                        if is_member:
                            projects.add(project_id)
                    except Exception as ex:
                        logger.warning(f"Failed to verify IAM policy for project {project_id}: {ex}")
            except Exception as e:
                logger.error(f"Error executing project-level permission discovery: {e}")

        # If the user has top-level organization/folder access, they have access to all org projects
        if has_top_level_access and settings.google_cloud_organization:
            org_projects = get_projects_in_org(settings.google_cloud_organization)
            projects.update(org_projects)

        # Update cache
        with self.cache_lock:
            self.user_projects_cache[user_email] = (now + CACHE_TTL_SECONDS, projects)

        logger.debug("Project discovery completed. Access allowed to: %s", list(projects))
        return projects


# Module-level singleton instance for project discovery caching and lookup
project_discovery_manager = ProjectDiscoveryManager()

# Maintain direct module references pointing to manager attributes for unit test compatibility
_USER_PROJECTS_CACHE = project_discovery_manager.user_projects_cache
_CACHE_LOCK = project_discovery_manager.cache_lock


def list_billing_projects(billing_account_name: str) -> list[str]:
    """Lists all projects associated with a given billing account.

    Args:
        billing_account_name: The resource name of the billing account,
            e.g., 'billingAccounts/012345-ABCDEF-012345'.

    Returns:
        A list of project IDs.
    """
    try:
        service = get_service("cloudbilling", "v1")

        logger.debug("Querying billingAccounts.projects.list for name=%s", billing_account_name)
        request = service.billingAccounts().projects().list(name=billing_account_name)
        projects = []

        while request is not None:
            response = request.execute()

            project_billing_info = response.get("projectBillingInfo", [])
            logger.debug("Billing account projects list returned %d items.", len(project_billing_info))
            if project_billing_info:
                logger.debug("Snippet of first project billing info: %s", project_billing_info[0])
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
    """Retrieves all project IDs within a given organization using Cloud Asset Inventory.

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
        logger.debug("Querying searchAllResources for org projects: scope=%s, assetTypes=%s", scope, asset_types)
        request = service.v1().searchAllResources(scope=scope, assetTypes=asset_types)

        while request is not None:
            response = request.execute()
            logger.debug("searchAllResources returned %d resource items.", len(response.get("results", [])))
            if response.get("results"):
                logger.debug("Snippet of first search resource: %s", response.get("results")[0])
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


def get_user_accessible_projects(user_email: str) -> set[str]:
    """Discovers all project IDs that the given user has access to."""
    return project_discovery_manager.get_user_accessible_projects(user_email)

