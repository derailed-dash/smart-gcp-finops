from unittest.mock import MagicMock, patch

import pytest
from finops_agent.app_utils.cai_utils import clear_services_cache
from finops_agent.app_utils.zombie_resources import search_zombie_resources


@pytest.fixture(autouse=True)
def setup_teardown():
    clear_services_cache()
    yield
    clear_services_cache()


@patch("googleapiclient.discovery.build")
def test_search_unattached_disks(mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_search_request = mock_service.v1().searchAllResources()
    mock_search_request.execute.return_value = {
        "results": [
            {
                "name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d1",
                "assetType": "compute.googleapis.com/Disk",
                "additionalAttributes": {},
            },
            {
                "name": "//compute.googleapis.com/projects/p1/zones/z1/disks/d2_attached",
                "assetType": "compute.googleapis.com/Disk",
                "additionalAttributes": {"users": ["some-user"]},
            },
        ]
    }
    mock_service.v1().searchAllResources_next.return_value = None

    results = search_zombie_resources("projects/test-project", "UNATTACHED_DISKS")

    # Should filter out the attached disk
    assert len(results) == 1
    assert (
        results[0]["name"] == "//compute.googleapis.com/projects/p1/zones/z1/disks/d1"
    )

    mock_service.v1().searchAllResources.assert_called_with(
        scope="projects/test-project",
        query="state=READY",
        assetTypes=["compute.googleapis.com/Disk"],
    )


@patch("googleapiclient.discovery.build")
def test_search_idle_ips(mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_search_request = mock_service.v1().searchAllResources()
    mock_search_request.execute.return_value = {
        "results": [
            {
                "name": "//compute.googleapis.com/projects/p1/regions/r1/addresses/a1",
                "assetType": "compute.googleapis.com/Address",
                "additionalAttributes": {},
            },
            {
                "name": "//compute.googleapis.com/projects/p1/regions/r1/addresses/a2_used",
                "assetType": "compute.googleapis.com/Address",
                "additionalAttributes": {"users": ["some-user"]},
            },
        ]
    }
    mock_service.v1().searchAllResources_next.return_value = None

    results = search_zombie_resources("projects/test-project", "IDLE_IPS")

    # Should filter out the used IP
    assert len(results) == 1
    assert (
        results[0]["name"]
        == "//compute.googleapis.com/projects/p1/regions/r1/addresses/a1"
    )

    mock_service.v1().searchAllResources.assert_called_with(
        scope="projects/test-project",
        query="state=RESERVED",
        assetTypes=["compute.googleapis.com/Address"],
    )


@patch("googleapiclient.discovery.build")
def test_search_zombie_resources_invalid_category(mock_build):
    results = search_zombie_resources("projects/test-project", "UNKNOWN_CATEGORY")
    assert results == []


@patch("googleapiclient.discovery.build")
def test_search_zombie_resources_exception(mock_build):
    mock_build.side_effect = Exception("Test Error")
    results = search_zombie_resources("projects/test-project", "UNATTACHED_DISKS")
    assert results == []
