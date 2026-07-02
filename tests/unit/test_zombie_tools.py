from unittest.mock import call, patch

import pytest
from finops_agent.app_utils.zombie_tools import clear_zombie_cache, list_zombie_resources
from finops_agent.config import settings


@pytest.fixture(autouse=True)
def clean_zombie_cache():
    clear_zombie_cache()
    yield
    clear_zombie_cache()


@patch("finops_agent.app_utils.zombie_tools.get_active_billing_projects")
@patch("finops_agent.app_utils.zombie_tools.list_billing_projects")
@patch("finops_agent.app_utils.zombie_tools.search_zombie_resources")
def test_list_zombie_resources_no_org(
    mock_search, mock_list_projects, mock_get_active_projects
):
    mock_get_active_projects.return_value = []
    mock_list_projects.return_value = ["project-a", "project-b"]

    # Mock search to return different results per project
    import threading

    mock_lock = threading.Lock()
    original_call = mock_search.__call__

    def locked_call(*args, **kwargs):
        with mock_lock:
            return original_call(*args, **kwargs)

    mock_search.__call__ = locked_call

    def side_effect(scope, category):
        if scope == "projects/project-a":
            return [{"name": "fake_disk_a"}]
        elif scope == "projects/project-b":
            return [{"name": "fake_disk_b"}]
        return []

    mock_search.side_effect = side_effect

    # Store old values
    old_billing_account = settings.google_cloud_billing_account
    old_org = settings.google_cloud_organization

    settings.google_cloud_billing_account = "012345-ABCDEF-012345"
    settings.google_cloud_organization = None  # Force the fallback loop

    try:
        results = list_zombie_resources("UNATTACHED_DISKS")

        assert len(results) == 2
        assert any(r["name"] == "fake_disk_a" for r in results)
        assert any(r["name"] == "fake_disk_b" for r in results)

        mock_list_projects.assert_called_once_with(
            "billingAccounts/012345-ABCDEF-012345"
        )
        assert mock_search.call_count == 2
    finally:
        # Restore old values
        settings.google_cloud_billing_account = old_billing_account
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.zombie_tools.get_active_billing_projects")
@patch("finops_agent.app_utils.zombie_tools.get_projects_in_org")
@patch("finops_agent.app_utils.zombie_tools.list_billing_projects")
@patch("finops_agent.app_utils.zombie_tools.search_zombie_resources")
def test_list_zombie_resources_with_org_optimized(
    mock_search, mock_list_projects, mock_get_org_projects, mock_get_active_projects
):
    """Test that projects in the org are skipped during individual project search."""
    mock_get_active_projects.return_value = []
    mock_list_projects.return_value = ["project-in-org", "project-outside-org"]
    mock_get_org_projects.return_value = {"project-in-org"}

    # Mock search results
    def side_effect(scope, category):
        if scope == "organizations/123456789":
            return [{"name": "disk_in_org"}]
        elif scope == "projects/project-outside-org":
            return [{"name": "disk_outside_org"}]
        return []

    mock_search.side_effect = side_effect

    # Store old values
    old_org = settings.google_cloud_organization
    settings.google_cloud_organization = "123456789"

    try:
        results = list_zombie_resources("UNATTACHED_DISKS")

        assert len(results) == 2
        assert any(r["name"] == "disk_in_org" for r in results)
        assert any(r["name"] == "disk_outside_org" for r in results)

        # Verify calls
        mock_search.assert_any_call(
            scope="organizations/123456789", category="UNATTACHED_DISKS"
        )
        mock_search.assert_any_call(
            scope="projects/project-outside-org", category="UNATTACHED_DISKS"
        )

        # CRITICAL: Verify project-in-org was NOT searched individually
        inside_project_call = call(
            scope="projects/project-in-org", category="UNATTACHED_DISKS"
        )
        assert inside_project_call not in mock_search.call_args_list
    finally:
        # Restore old values
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.zombie_tools.bigquery.Client")
@patch("finops_agent.app_utils.zombie_tools.get_credentials")
def test_get_active_billing_projects(mock_get_credentials, mock_bq_client_class):
    from unittest.mock import MagicMock

    from finops_agent.app_utils.zombie_tools import get_active_billing_projects

    mock_get_credentials.return_value = MagicMock()

    mock_client = MagicMock()
    mock_bq_client_class.return_value = mock_client

    mock_row_1 = MagicMock()
    mock_row_1.id = "active-project-1"
    mock_row_2 = MagicMock()
    mock_row_2.id = "active-project-2"

    mock_job = MagicMock()
    mock_job.result.return_value = [mock_row_1, mock_row_2]
    mock_client.query.return_value = mock_job

    projects = get_active_billing_projects()

    assert projects == ["active-project-1", "active-project-2"]
    mock_client.query.assert_called_once()


@patch("finops_agent.app_utils.zombie_tools.search_zombie_resources")
def test_list_zombie_resources_scoped_project(mock_search):
    mock_search.return_value = [{"name": "fake_disk_scoped"}]

    results = list_zombie_resources("UNATTACHED_DISKS", project_id="my-scoped-project")

    assert len(results) == 1
    assert results[0]["name"] == "fake_disk_scoped"

    mock_search.assert_called_once_with(
        scope="projects/my-scoped-project", category="UNATTACHED_DISKS"
    )
