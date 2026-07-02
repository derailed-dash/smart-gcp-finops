from unittest.mock import MagicMock, patch

import pytest
from finops_agent.app_utils.cai_utils import (
    clear_services_cache,
    enrich_with_cai_metadata,
    get_asset_history,
)


@pytest.fixture(autouse=True)
def setup_teardown():
    clear_services_cache()
    yield
    clear_services_cache()


@patch("finops_agent.app_utils.cai_utils.discovery.build")
def test_enrich_with_cai_metadata(mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_search_request = mock_service.v1().searchAllResources()
    mock_search_request.execute.return_value = {
        "results": [
            {
                "name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
                "assetType": "compute.googleapis.com/Disk",
                "state": "READY",
            }
        ]
    }
    mock_service.v1().searchAllResources_next.return_value = None

    cost_records = [
        {
            "cost": 10.5,
            "resource_name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
        },
        {
            "cost": 5.0,
            "resource_name": "//compute.googleapis.com/projects/p1/zones/z1/disks/unknown",
        },
    ]

    enriched = enrich_with_cai_metadata(cost_records, "projects/test-project")

    assert len(enriched) == 2
    assert enriched[0]["cai_metadata"]["state"] == "READY"
    assert "cai_metadata" not in enriched[1] or enriched[1]["cai_metadata"] is None


@patch("finops_agent.app_utils.cai_utils.discovery.build")
def test_get_asset_history(mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_history_request = mock_service.v1().batchGetAssetsHistory()
    mock_history_request.execute.return_value = {
        "assets": [
            {
                "asset": {
                    "name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
                    "assetType": "compute.googleapis.com/Disk",
                },
                "window": {"startTime": "2026-04-01T00:00:00Z"},
            }
        ]
    }

    history = get_asset_history(
        "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
        "projects/test-project",
        "2026-04-01T00:00:00Z",
    )

    assert len(history) == 1
    assert (
        history[0]["asset"]["name"]
        == "//compute.googleapis.com/projects/p1/zones/z1/disks/d1"
    )


@patch("finops_agent.app_utils.cai_utils.discovery.build")
def test_enrich_with_cai_metadata_chunking(mock_build):
    """Verify that large resource lists are chunked correctly."""
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    # Simulate 25 resource names to force two chunks (20 + 5)
    resource_names = [
        f"//compute.googleapis.com/projects/p1/zones/z1/disks/d{i}" for i in range(25)
    ]
    cost_records = [{"resource_name": name} for name in resource_names]

    # Mock the API to return a minimal result for any query
    mock_search_request = mock_service.v1().searchAllResources.return_value
    mock_search_request.execute.return_value = {"results": []}
    mock_service.v1().searchAllResources_next.return_value = None

    _ = enrich_with_cai_metadata(cost_records, "projects/test-project")

    # Assert that the search was called twice (once for each chunk)
    assert mock_service.v1().searchAllResources.call_count == 2

    # Check the query string for the first chunk (20 items)
    first_call_query = (
        mock_service.v1().searchAllResources.call_args_list[0].kwargs["query"]
    )
    assert len(first_call_query.split(" OR ")) == 20

    # Check the query string for the second chunk (5 items)
    second_call_query = (
        mock_service.v1().searchAllResources.call_args_list[1].kwargs["query"]
    )
    assert len(second_call_query.split(" OR ")) == 5
