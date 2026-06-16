from unittest.mock import patch

from fastapi.testclient import TestClient

from app.fast_api_app import app

client = TestClient(app)


@patch("app.app_utils.dashboard_data.get_actual_dashboard_metrics")
def test_get_dashboard_endpoint(mock_get_metrics):
    """Verify that /api/dashboard endpoint works and correctly passes query params."""
    mock_metrics = {
        "currency": "GBP",
        "mtdSpend": 60.52,
        "mtdChange": 12.4,
        "forecast": 64.69,
        "forecastLabel": "Projected end-of-month",
        "anomaliesCount": 2,
        "zombieWaste": 0.0,
        "recentSpikes": [],
        "zombies": [],
        "explorer": [],
    }
    mock_get_metrics.return_value = mock_metrics

    # Test request without query parameters
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json() == mock_metrics
    mock_get_metrics.assert_called_once_with(client_day=None, client_month_days=None)

    mock_get_metrics.reset_mock()

    # Test request with clientDay and clientMonthDays query parameters
    response_custom = client.get("/api/dashboard?clientDay=29&clientMonthDays=31")
    assert response_custom.status_code == 200
    assert response_custom.json() == mock_metrics
    mock_get_metrics.assert_called_once_with(client_day=29, client_month_days=31)


@patch("app.app_utils.dashboard_data.get_actual_dashboard_metrics")
def test_get_dashboard_endpoint_exception(mock_get_metrics):
    """Verify that /api/dashboard returns fallback response on exceptions."""
    mock_get_metrics.side_effect = Exception("BigQuery connection failed")

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["forecast"] == 0.0
    assert data["forecastLabel"] == "Projected end-of-month"
    assert data["mtdSpend"] == 0.0
