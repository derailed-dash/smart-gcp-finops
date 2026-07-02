from datetime import UTC, datetime, timedelta
from unittest.mock import call, patch

import pytest
from finops_agent.app_utils.cai_tools import (
    clear_cai_caches,
    get_cai_history_for_resource,
    get_cai_metadata_for_resources,
)
from finops_agent.config import settings


@pytest.fixture(autouse=True)
def clean_cai_caches():
    clear_cai_caches()
    yield
    clear_cai_caches()


@patch("finops_agent.app_utils.cai_tools.list_billing_projects")
@patch("finops_agent.app_utils.cai_tools.enrich_with_cai_metadata")
def test_get_cai_metadata_for_resources_grouping(mock_enrich, mock_list_projects):
    # Store old setting
    old_org = settings.google_cloud_organization
    settings.google_cloud_organization = None

    try:
        # Mock the return value of enrich_with_cai_metadata per project
        def side_effect(records, scope):
            if scope == "projects/p1":
                return [
                    {
                        "resource_name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
                        "cai_metadata": {"state": "READY"},
                    }
                ]
            elif scope == "projects/p2":
                return [
                    {
                        "resource_name": "//compute.googleapis.com/projects/p2/zones/z1/disks/d2",
                        "cai_metadata": {"state": "IN_USE"},
                    }
                ]
            return []

        mock_enrich.side_effect = side_effect

        result = get_cai_metadata_for_resources(
            [
                "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
                "//compute.googleapis.com/projects/p2/zones/z1/disks/d2",
            ]
        )

        assert len(result) == 2
        mock_list_projects.assert_not_called()  # We extract from the name
        assert mock_enrich.call_count == 2
    finally:
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.cai_tools.list_billing_projects")
@patch("finops_agent.app_utils.cai_tools.enrich_with_cai_metadata")
def test_get_cai_metadata_for_resources_org_scope(mock_enrich, mock_list_projects):
    # Store old setting
    old_org = settings.google_cloud_organization
    settings.google_cloud_organization = "12345678"

    try:
        # Mock the return value of enrich_with_cai_metadata per project
        mock_enrich.return_value = [
            {
                "resource_name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
                "cai_metadata": {"state": "READY"},
            }
        ]

        result = get_cai_metadata_for_resources(
            ["//compute.googleapis.com/projects/p1/zones/z1/disks/d1"]
        )

        assert len(result) == 1
        mock_list_projects.assert_not_called()
        mock_enrich.assert_called_once_with(
            [{"resource_name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1"}],
            "organizations/12345678",
        )
    finally:
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.cai_tools.list_billing_projects")
@patch("finops_agent.app_utils.cai_tools.get_asset_history")
def test_get_cai_history_for_resource(mock_history, mock_list_projects):
    old_org = settings.google_cloud_organization
    settings.google_cloud_organization = None

    try:
        mock_history.return_value = [
            {"asset": {"name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1"}}
        ]

        # Use a dynamic time (10 days ago) within the 35-day window to prevent defensive override
        dynamic_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()

        _ = get_cai_history_for_resource(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1", dynamic_time
        )

        mock_list_projects.assert_not_called()  # We extract from the name, no need to list
        mock_history.assert_called_once_with(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
            "projects/p1",
            dynamic_time,
            None,
        )
    finally:
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.cai_tools.list_billing_projects")
@patch("finops_agent.app_utils.cai_tools.get_asset_history")
def test_get_cai_history_for_resource_older_than_35_days(mock_history, mock_list_projects):
    mock_history.return_value = []

    # Request a time 100 days ago
    old_time = (datetime.now(UTC) - timedelta(days=100)).isoformat()

    _ = get_cai_history_for_resource(
        "//compute.googleapis.com/projects/p1/zones/z1/disks/d1", old_time
    )

    # Extract the requested time that was passed to the API
    called_time_str = mock_history.call_args[0][2]
    called_time = datetime.fromisoformat(called_time_str)

    # It should be at least 34 days ago, but definitely not 100 days ago
    now = datetime.now(UTC)
    delta = now - called_time
    assert 34 <= delta.days <= 36


@patch("finops_agent.app_utils.cai_tools.list_billing_projects")
@patch("finops_agent.app_utils.cai_tools.enrich_with_cai_metadata")
def test_get_cai_metadata_for_resources_hybrid(mock_enrich, mock_list_projects):
    # Store old setting
    old_org = settings.google_cloud_organization
    settings.google_cloud_organization = "12345678"

    try:
        # Mock the return value:
        # d1 is in the org, d2 is NOT in the org but in project p2
        def side_effect(records, scope):
            if scope == "organizations/12345678":
                return [
                    {
                        "resource_name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
                        "cai_metadata": {"state": "READY"},
                    }
                ]
            elif scope == "projects/p2":
                return [
                    {
                        "resource_name": "//compute.googleapis.com/projects/p2/zones/z1/disks/d2",
                        "cai_metadata": {"state": "IN_USE"},
                    }
                ]
            return []

        mock_enrich.side_effect = side_effect

        result = get_cai_metadata_for_resources(
            [
                "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
                "//compute.googleapis.com/projects/p2/zones/z1/disks/d2",
            ]
        )

        assert len(result) == 2

        # Verify the organization scope was called with all names
        org_call = next(
            call
            for call in mock_enrich.call_args_list
            if len(call.args) > 1 and call.args[1] == "organizations/12345678"
        )
        # Convert to set for order-insensitive comparison
        org_called_names = {r["resource_name"] for r in org_call.args[0]}
        assert org_called_names == {
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
            "//compute.googleapis.com/projects/p2/zones/z1/disks/d2",
        }

        # Verify the project scope was called with only the remaining name
        mock_enrich.assert_any_call(
            [{"resource_name": "//compute.googleapis.com/projects/p2/zones/z1/disks/d2"}],
            "projects/p2",
        )
    finally:
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.cai_tools.list_billing_projects")
@patch("finops_agent.app_utils.cai_tools.get_asset_history")
def test_get_cai_history_for_resource_project_first_success(mock_history, mock_list_projects):
    old_org = settings.google_cloud_organization
    settings.google_cloud_organization = "12345678"

    try:
        mock_history.return_value = [{"asset": {"name": "d1"}}]

        dynamic_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        _ = get_cai_history_for_resource(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1", dynamic_time
        )

        # Should query project scope p1 first and succeed, hence NOT calling organization scope
        mock_history.assert_called_once_with(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
            "projects/p1",
            dynamic_time,
            None,
        )
    finally:
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.cai_tools.list_billing_projects")
@patch("finops_agent.app_utils.cai_tools.get_asset_history")
def test_get_cai_history_for_resource_with_org_fallback(mock_history, mock_list_projects):
    old_org = settings.google_cloud_organization
    settings.google_cloud_organization = "12345678"

    try:
        # Project returns empty, Org returns the result
        def side_effect(resource_name, scope, start_time, end_time):
            if scope == "projects/p1":
                return []
            return [{"asset": {"name": resource_name}}]

        mock_history.side_effect = side_effect

        dynamic_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        _ = get_cai_history_for_resource(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1", dynamic_time
        )

        # Verification of fallback call sequence: project first, then organization
        mock_history.assert_any_call(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
            "projects/p1",
            dynamic_time,
            None,
        )
        mock_history.assert_any_call(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
            "organizations/12345678",
            dynamic_time,
            None,
        )
    finally:
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.cai_tools.is_org_scope_disabled")
@patch("finops_agent.app_utils.cai_tools.list_billing_projects")
@patch("finops_agent.app_utils.cai_tools.get_asset_history")
def test_get_cai_history_for_resource_org_disabled(
    mock_history, mock_list_projects, mock_is_org_disabled
):
    old_org = settings.google_cloud_organization
    settings.google_cloud_organization = "12345678"
    mock_is_org_disabled.return_value = True

    try:
        mock_history.return_value = []

        dynamic_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        _ = get_cai_history_for_resource(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1", dynamic_time
        )

        # Should call project scope first
        mock_history.assert_any_call(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
            "projects/p1",
            dynamic_time,
            None,
        )
        # Should NOT call organization scope since it is marked disabled
        org_call = call(
            "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
            "organizations/12345678",
            dynamic_time,
            None,
        )
        assert org_call not in mock_history.call_args_list
    finally:
        settings.google_cloud_organization = old_org


@patch("finops_agent.app_utils.cai_tools.logger")
@patch("finops_agent.app_utils.cai_tools.get_asset_history")
def test_get_cai_history_for_resource_caching_and_logging(mock_history, mock_logger):
    mock_history.return_value = [{"asset": {"name": "d1"}}]
    dynamic_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()

    # First call: cache miss
    res1 = get_cai_history_for_resource(
        "//compute.googleapis.com/projects/p1/zones/z1/disks/d1", dynamic_time
    )
    # Second call: cache hit
    res2 = get_cai_history_for_resource(
        "//compute.googleapis.com/projects/p1/zones/z1/disks/d1", dynamic_time
    )

    assert res1 == res2
    assert mock_history.call_count == 1  # Verify cache worked

    # Verify logger calls
    mock_logger.debug.assert_any_call(
        "Requesting CAI history: resource_name=%s, start_time=%s, end_time=%s",
        "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
        dynamic_time,
        None,
    )
    mock_logger.debug.assert_any_call(
        "CAI history cache hit for resource: %s (returned %d records)",
        "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
        1,
    )
