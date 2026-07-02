from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from finops_agent.app_utils.dashboard_data import (
    classify_project,
    estimate_zombie_cost,
    get_actual_dashboard_metrics,
)


def test_classify_project():
    assert classify_project("my-project-dev") == "dev"
    assert classify_project("scratch-12345") == "dev"
    assert classify_project("finops-admin-dev") == "dev"
    assert classify_project("vpc-host-npd-dzb1") == "dev"

    assert classify_project("my-project-staging") == "staging"
    assert classify_project("stg-database") == "staging"

    assert classify_project("my-project-prod") == "prod"
    assert classify_project("dazbo-portfolio") == "prod"


def test_estimate_zombie_cost():
    # Disks with parsed sizes
    assert (
        estimate_zombie_cost({"additionalAttributes": {"size": "100 GB"}}, "UNATTACHED_DISKS")
        == 10.0
    )
    assert (
        estimate_zombie_cost({"additionalAttributes": {"size": "500 GiB"}}, "UNATTACHED_DISKS")
        == 50.0
    )
    # Disk with unknown size defaults to 40.0
    assert estimate_zombie_cost({}, "UNATTACHED_DISKS") == 40.0

    # IPs default to 15.0
    assert estimate_zombie_cost({}, "IDLE_IPS") == 15.0


@patch("finops_agent.app_utils.dashboard_data.list_zombie_resources")
@patch("finops_agent.app_utils.dashboard_data.bigquery.Client")
@patch("finops_agent.app_utils.dashboard_data.default")
def test_get_actual_dashboard_metrics(mock_default, mock_bq_client_class, mock_list_zombies):
    mock_default.return_value = (MagicMock(), "fake-project")

    # Mock BigQuery Client and query results
    mock_client = MagicMock()
    mock_bq_client_class.return_value = mock_client

    # Setup month query mock results
    mock_month_row_1 = MagicMock()
    mock_month_row_1.billing_month = datetime.now().strftime("%Y-%m")
    mock_month_row_1.monthly_cost = 1000.0

    mock_month_row_2 = MagicMock()
    prev_month = datetime.now().replace(day=1) - timedelta(days=1)
    mock_month_row_2.billing_month = prev_month.strftime("%Y-%m")
    mock_month_row_2.monthly_cost = 800.0

    # Setup daily query mock results
    mock_daily_row_1 = MagicMock()
    mock_daily_row_1.usage_date = datetime.now().date()
    mock_daily_row_1.service_description = "Cloud Run"
    mock_daily_row_1.daily_cost = 50.0

    mock_daily_row_2 = MagicMock()
    mock_daily_row_2.usage_date = datetime.now().date()
    mock_daily_row_2.service_description = "Gemini API"
    mock_daily_row_2.daily_cost = 150.0

    # Setup explorer query mock results
    mock_exp_row_1 = MagicMock()
    mock_exp_row_1.project_id = "dazbo-portfolio"
    mock_exp_row_1.service_description = "Compute Engine"
    mock_exp_row_1.billing_month = datetime.now().strftime("%Y-%m")
    mock_exp_row_1.monthly_cost = 600.0

    # Configure mock query execution side effects
    def query_side_effect(sql):
        mock_job = MagicMock()
        if "project.id as project_id" in sql:
            mock_job.result.return_value = [mock_exp_row_1]
        elif "MAX(usage_start_time)" in sql:
            mock_max_row = MagicMock()
            mock_max_row.max_day = datetime.now().day
            mock_job.result.return_value = [mock_max_row]
        elif "FORMAT_TIMESTAMP" in sql:
            mock_job.result.return_value = [mock_month_row_1, mock_month_row_2]
        elif "DATE(usage_start_time)" in sql:
            mock_job.result.return_value = [mock_daily_row_1, mock_daily_row_2]
        else:
            mock_job.result.return_value = []
        return mock_job

    mock_client.query.side_effect = query_side_effect

    # Mock zombie tools
    def zombies_side_effect(category):
        if category == "UNATTACHED_DISKS":
            return [
                {
                    "name": "projects/p1/disks/disk-1",
                    "displayName": "disk-1",
                    "project": "projects/p1",
                    "additionalAttributes": {"size": "200 GB"},
                }
            ]
        return []

    mock_list_zombies.side_effect = zombies_side_effect

    # Run the function
    metrics = get_actual_dashboard_metrics()

    # Verifications
    assert metrics["mtdSpend"] == 1000.0
    assert metrics["mtdChange"] == 25.0  # (1000 - 800) / 800 * 100
    assert metrics["zombieWaste"] == 20.0  # 200 GB * 0.10
    assert len(metrics["zombies"]) == 1
    assert metrics["zombies"][0]["name"] == "disk-1"
    assert metrics["zombies"][0]["cost"] == 20.0
    assert len(metrics["explorer"]) == 1
    assert metrics["explorer"][0]["project"] == "dazbo-portfolio"
    assert metrics["explorer"][0]["cost"] == 600.0

    # Verify the telemetry-based forecast linear projection
    import calendar

    now = datetime.now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    expected_forecast = round((1000.0 / now.day) * days_in_month, 2)
    assert metrics["forecast"] == expected_forecast

    # Verify that explicit client_day and client_month_days are prioritized correctly
    metrics_custom = get_actual_dashboard_metrics(client_day=15, client_month_days=30)
    assert metrics_custom["forecast"] == 2000.0


@patch("finops_agent.app_utils.dashboard_data.list_zombie_resources")
@patch("finops_agent.app_utils.dashboard_data.bigquery.Client")
@patch("finops_agent.app_utils.dashboard_data.default")
def test_get_actual_dashboard_metrics_with_allowed_projects(
    mock_default, mock_bq_client_class, mock_list_zombies
):
    """Test get_actual_dashboard_metrics scopes costs and zombies to allowed projects."""
    mock_default.return_value = (MagicMock(), "fake-project")
    mock_client = MagicMock()
    mock_bq_client_class.return_value = mock_client

    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_client.query.return_value = mock_job

    mock_list_zombies.return_value = [
        {
            "name": "projects/p1/disks/disk-1",
            "displayName": "disk-1",
            "project": "projects/p1",
            "additionalAttributes": {"size": "200 GB"},
        },
        {
            "name": "projects/p2/disks/disk-2",
            "displayName": "disk-2",
            "project": "projects/p2",
            "additionalAttributes": {"size": "200 GB"},
        },
    ]

    allowed_projects = {"p1"}
    metrics = get_actual_dashboard_metrics(allowed_projects=allowed_projects)

    called_sql = mock_client.query.call_args[0][0]
    assert "project.id IN ('p1')" in called_sql

    assert len(metrics["zombies"]) == 2
    assert all(z["project"] == "p1" for z in metrics["zombies"])
