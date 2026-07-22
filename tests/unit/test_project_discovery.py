from unittest.mock import ANY, MagicMock, patch

import pytest
from finops_agent.app_utils.cai_utils import clear_services_cache
from finops_agent.app_utils.project_discovery import (
    _USER_PROJECTS_CACHE,
    get_projects_in_org,
    list_billing_projects,
)


@pytest.fixture(autouse=True)
def setup_teardown():
    clear_services_cache()
    yield
    clear_services_cache()


@patch("googleapiclient.discovery.build")
def test_list_billing_projects_success(mock_build):
    """Test successful project discovery for a billing account."""
    # Setup mock
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_list_request = mock_service.billingAccounts().projects().list()
    mock_list_request.execute.return_value = {
        "projectBillingInfo": [{"projectId": "project-1"}, {"projectId": "project-2"}]
    }

    # Ensure pagination terminates
    mock_service.billingAccounts().projects().list_next.return_value = None

    # Execute
    projects = list_billing_projects("billingAccounts/012345-ABCDEF-012345")

    # Verify
    assert projects == ["project-1", "project-2"]
    mock_build.assert_called_with("cloudbilling", "v1", credentials=ANY, cache_discovery=False)


@patch("googleapiclient.discovery.build")
def test_list_billing_projects_empty(mock_build):
    """Test project discovery when no projects are found."""
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_list_request = mock_service.billingAccounts().projects().list()
    mock_list_request.execute.return_value = {}

    # Ensure pagination terminates
    mock_service.billingAccounts().projects().list_next.return_value = None

    projects = list_billing_projects("billingAccounts/012345-ABCDEF-012345")

    assert projects == []


@patch("googleapiclient.discovery.build")
def test_get_projects_in_org_success(mock_build):
    """Test successful project listing within an organization."""
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_search_request = mock_service.v1().searchAllResources()
    mock_search_request.execute.return_value = {
        "results": [
            {"name": "//cloudresourcemanager.googleapis.com/projects/org-project-1"},
            {"name": "//cloudresourcemanager.googleapis.com/projects/org-project-2"},
        ]
    }
    # Ensure pagination terminates
    mock_service.v1().searchAllResources_next.return_value = None

    projects = get_projects_in_org("123456789")

    assert projects == {"org-project-1", "org-project-2"}
    mock_build.assert_called_with("cloudasset", "v1", credentials=ANY, cache_discovery=False)


@patch("finops_agent.app_utils.project_discovery.get_service")
@patch("finops_agent.app_utils.project_discovery.settings")
def test_get_user_accessible_projects_org(mock_settings, mock_get_service):
    """Test get_user_accessible_projects using organization Cloud Asset IAM policy search."""
    from finops_agent.app_utils.project_discovery import (
        _USER_PROJECTS_CACHE,
        get_user_accessible_projects,
    )

    _USER_PROJECTS_CACHE.clear()
    mock_settings.google_cloud_organization = "123456789"
    mock_settings.google_cloud_billing_account = None

    mock_service = MagicMock()
    mock_get_service.return_value = mock_service

    # Setup searchAllIamPolicies response
    mock_request = mock_service.v1().searchAllIamPolicies()
    mock_request.execute.return_value = {
        "results": [
            {"resource": "//cloudresourcemanager.googleapis.com/projects/allowed-project-1"},
            {"resource": "//cloudresourcemanager.googleapis.com/projects/allowed-project-2"},
        ]
    }
    mock_service.v1().searchAllIamPolicies_next.return_value = None

    projects = get_user_accessible_projects("test-user@dazbo.co.uk")
    assert projects == {"allowed-project-1", "allowed-project-2"}


@patch("finops_agent.app_utils.project_discovery._get_asset_v1_client")
@patch("finops_agent.app_utils.project_discovery.list_billing_projects")
@patch("finops_agent.app_utils.project_discovery.get_service")
@patch("finops_agent.app_utils.project_discovery.settings")
def test_get_user_accessible_projects_standalone(
    mock_settings, mock_get_service, mock_list_billing, mock_get_asset_client
):
    """Test get_user_accessible_projects in standalone mode using project-level IAM policies."""
    from finops_agent.app_utils.project_discovery import get_user_accessible_projects

    # Ensure asset_v1 client raises an error to trigger CRM fallback
    mock_asset_inst = MagicMock()
    mock_asset_inst.search_all_iam_policies.side_effect = Exception("Asset API forbidden")
    mock_get_asset_client.return_value = mock_asset_inst

    _USER_PROJECTS_CACHE.clear()
    mock_settings.google_cloud_organization = None
    mock_settings.google_cloud_billing_account = "012345-ABCDEF-012345"

    mock_list_billing.return_value = ["proj-a", "proj-b"]

    mock_service = MagicMock()
    mock_get_service.return_value = mock_service

    # Configure getIamPolicy responses:
    # User has access to proj-a, but not proj-b
    mock_policy_a = {
        "bindings": [{"role": "roles/viewer", "members": ["user:test-user@dazbo.co.uk"]}]
    }
    mock_policy_b = {
        "bindings": [{"role": "roles/viewer", "members": ["user:some-other-user@dazbo.co.uk"]}]
    }

    def get_iam_policy_side_effect(resource):
        req = MagicMock()
        if resource == "proj-a":
            req.execute.return_value = mock_policy_a
        else:
            req.execute.return_value = mock_policy_b
        return req

    mock_service.projects().getIamPolicy.side_effect = get_iam_policy_side_effect

    projects = get_user_accessible_projects("test-user@dazbo.co.uk")
    assert projects == {"proj-a"}


@patch("finops_agent.app_utils.project_discovery._get_asset_v1_client")
@patch("finops_agent.app_utils.project_discovery.list_billing_projects")
@patch("finops_agent.app_utils.project_discovery.get_service")
@patch("finops_agent.app_utils.project_discovery.settings")
def test_get_user_accessible_projects_cli_user(
    mock_settings, mock_get_service, mock_list_billing, mock_get_asset_client
):
    """Test that 'cli-user' is mapped to settings.local_developer_email."""
    from finops_agent.app_utils.project_discovery import get_user_accessible_projects

    mock_asset_inst = MagicMock()
    mock_asset_inst.search_all_iam_policies.side_effect = Exception("Asset API forbidden")
    mock_get_asset_client.return_value = mock_asset_inst

    _USER_PROJECTS_CACHE.clear()
    mock_settings.google_cloud_organization = None
    mock_settings.google_cloud_billing_account = "012345-ABCDEF-012345"
    mock_settings.local_developer_email = "test-user@dazbo.co.uk"

    mock_list_billing.return_value = ["proj-a"]

    mock_service = MagicMock()
    mock_get_service.return_value = mock_service

    mock_policy_a = {
        "bindings": [{"role": "roles/viewer", "members": ["user:test-user@dazbo.co.uk"]}]
    }
    mock_service.projects().getIamPolicy().execute.return_value = mock_policy_a

    projects = get_user_accessible_projects("cli-user")
    assert projects == {"proj-a"}


@patch("finops_agent.app_utils.project_discovery._get_asset_v1_client")
@patch("finops_agent.app_utils.project_discovery.list_billing_projects")
@patch("finops_agent.app_utils.project_discovery.get_service")
@patch("finops_agent.app_utils.project_discovery.settings")
def test_get_user_accessible_projects_includes_orgless_and_filters_deleted(
    mock_settings, mock_get_service, mock_list_billing, mock_get_asset_client
):
    """Test that get_user_accessible_projects merges billing-linked (orgless) projects

    and excludes projects that are deleted/inactive according to Cloud Resource Manager.
    """
    from finops_agent.app_utils.project_discovery import (
        _USER_PROJECTS_CACHE,
        get_user_accessible_projects,
    )

    mock_asset_inst = MagicMock()
    mock_asset_inst.search_all_iam_policies.side_effect = Exception("Asset API forbidden")
    mock_get_asset_client.return_value = mock_asset_inst

    _USER_PROJECTS_CACHE.clear()
    mock_settings.google_cloud_organization = "123456789"
    mock_settings.google_cloud_billing_account = "012345-ABCDEF-012345"

    # Mock list_billing_projects to return both an active orgless project and a deleted project
    mock_list_billing.return_value = ["active-orgless-project", "deleted-tf-generator-prd"]

    # Mock get_service for cloudasset and cloudresourcemanager
    mock_asset_service = MagicMock()
    mock_crm_service = MagicMock()

    def get_service_side_effect(name, version):
        if name == "cloudasset":
            return mock_asset_service
        return mock_crm_service

    mock_get_service.side_effect = get_service_side_effect

    # 1. Cloud Asset searchAllIamPolicies returns org project
    mock_asset_req = mock_asset_service.v1().searchAllIamPolicies()
    mock_asset_req.execute.return_value = {
        "results": [
            {"resource": "//cloudresourcemanager.googleapis.com/projects/active-org-project"},
            {"resource": "//cloudresourcemanager.googleapis.com/projects/deleted-tf-generator-prd"},
        ]
    }
    mock_asset_service.v1().searchAllIamPolicies_next.return_value = None

    # 2. Cloud Resource Manager projects.list(filter="lifecycleState:ACTIVE") returns ONLY active projects
    mock_crm_list_req = mock_crm_service.projects().list()
    mock_crm_list_req.execute.return_value = {
        "projects": [
            {"projectId": "active-org-project", "lifecycleState": "ACTIVE"},
            {"projectId": "active-orgless-project", "lifecycleState": "ACTIVE"},
        ]
    }
    mock_crm_service.projects().list_next.return_value = None

    # Mock getIamPolicy for billing-linked project check
    mock_crm_service.projects().getIamPolicy().execute.return_value = {
        "bindings": [{"role": "roles/viewer", "members": ["user:test-user@dazbo.co.uk"]}]
    }

    projects = get_user_accessible_projects("test-user@dazbo.co.uk")

    # Verify: active-org-project and active-orgless-project must be included
    assert "active-org-project" in projects
    assert "active-orgless-project" in projects

    # Verify: deleted-tf-generator-prd MUST be excluded
    assert "deleted-tf-generator-prd" not in projects
    assert projects == {"active-org-project", "active-orgless-project"}

