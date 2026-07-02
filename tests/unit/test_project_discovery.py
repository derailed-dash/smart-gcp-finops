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
    from finops_agent.app_utils.project_discovery import get_user_accessible_projects

    _USER_PROJECTS_CACHE.clear()
    mock_settings.google_cloud_organization = "123456789"

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


@patch("finops_agent.app_utils.project_discovery.list_billing_projects")
@patch("finops_agent.app_utils.project_discovery.get_service")
@patch("finops_agent.app_utils.project_discovery.settings")
def test_get_user_accessible_projects_standalone(
    mock_settings, mock_get_service, mock_list_billing
):
    """Test get_user_accessible_projects in standalone mode using project-level IAM policies."""
    from finops_agent.app_utils.project_discovery import get_user_accessible_projects

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
