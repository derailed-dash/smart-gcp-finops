from unittest.mock import ANY, MagicMock, patch

import pytest

from app.app_utils.cai_utils import clear_services_cache
from app.app_utils.project_discovery import get_projects_in_org, list_billing_projects


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
    mock_build.assert_called_with(
        "cloudbilling", "v1", credentials=ANY, cache_discovery=False
    )


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
    mock_build.assert_called_with(
        "cloudasset", "v1", credentials=ANY, cache_discovery=False
    )
