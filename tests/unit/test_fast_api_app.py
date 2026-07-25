from unittest.mock import ANY, patch

from fastapi.testclient import TestClient

from bff.fast_api_app import app

client = TestClient(app)


@patch("finops_agent.app_utils.dashboard_data.get_actual_dashboard_metrics")
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
    mock_get_metrics.assert_called_once_with(
        allowed_projects=ANY, client_day=None, client_month_days=None, days=30
    )

    mock_get_metrics.reset_mock()

    # Test request with clientDay, clientMonthDays, and days query parameters
    response_custom = client.get("/api/dashboard?clientDay=29&clientMonthDays=31&days=14")
    assert response_custom.status_code == 200
    assert response_custom.json() == mock_metrics
    mock_get_metrics.assert_called_once_with(
        allowed_projects=ANY, client_day=29, client_month_days=31, days=14
    )


@patch("finops_agent.app_utils.dashboard_data.get_actual_dashboard_metrics")
def test_get_dashboard_endpoint_exception(mock_get_metrics):
    """Verify that /api/dashboard returns fallback response on exceptions."""
    mock_get_metrics.side_effect = Exception("BigQuery connection failed")

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["forecast"] == 0.0
    assert data["forecastLabel"] == "Projected end-of-month"
    assert data["mtdSpend"] == 0.0


def test_chat_stream_local():
    """Verify that chat stream routes to local runner when AGENT_RUNTIME_ID is unset."""
    from unittest.mock import MagicMock

    from bff.fast_api_app import app

    mock_runner = MagicMock()
    mock_runner.run.return_value = []

    # Store old runner
    old_runner = getattr(app.state, "runner", None)
    app.state.runner = mock_runner

    try:
        with patch.dict("os.environ", {}, clear=True):
            response = client.post("/api/chat/stream", json={"message": "hello"})
            assert response.status_code == 200
            content = response.text
            assert "dynamic billing table discovery" in content
    finally:
        if old_runner is not None:
            app.state.runner = old_runner


@patch("vertexai.Client")
@patch("google.adk.events.event.Event.model_validate")
def test_chat_stream_remote(mock_model_validate, mock_vertex_client):
    """Verify that chat stream routes to Agent Runtime when AGENT_RUNTIME_ID is set."""
    from unittest.mock import MagicMock

    # Mock Event model validation to return a dummy Event
    mock_event = MagicMock()
    mock_part = MagicMock()
    mock_part.text = "Hello from Remote Agent Runtime!"
    mock_event.content.parts = [mock_part]
    mock_event.is_final_response.return_value = False
    mock_model_validate.return_value = mock_event

    # Mock Vertex AI client and Agent Runtime
    mock_client_instance = MagicMock()
    mock_vertex_client.return_value = mock_client_instance
    mock_engine = MagicMock()
    mock_client_instance.agent_engines.get.return_value = mock_engine

    # Mock async stream query response
    async def mock_async_stream(**kwargs):
        yield {"content": "dummy"}

    async def mock_async_create_session(**kwargs):
        return {"id": "remote-session-123"}

    mock_engine.async_stream_query = mock_async_stream
    mock_engine.async_create_session = mock_async_create_session

    with patch.dict(
        "os.environ",
        {"AGENT_RUNTIME_ID": "projects/123/locations/europe-west1/reasoningEngines/456"},
        clear=True,
    ):
        response = client.post("/api/chat/stream", json={"message": "hello"})
        assert response.status_code == 200
        content = response.text
        assert "Routing query to Gemini Enterprise Agent Runtime" in content
        assert "Hello from Remote Agent Runtime!" in content


def test_get_status_endpoint():
    """Verify that /api/status endpoint returns correct status payload depending on env vars."""
    # Test local mode
    with patch.dict("os.environ", {}, clear=True):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["agent_name"] == "finops_agent"
        assert data["mode"] == "local"
        assert "agent_runtime_id" not in data
        assert "project_id" not in data

    # Test remote mode
    with patch.dict(
        "os.environ",
        {"AGENT_RUNTIME_ID": "projects/123/locations/us-central1/reasoningEngines/456"},
        clear=True,
    ):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["agent_name"] == "finops_agent"
        assert data["mode"] == "remote"
        assert data["agent_runtime_id"] == "projects/123/locations/us-central1/reasoningEngines/456"
        assert "project_id" not in data


@patch("finops_agent.app_utils.dashboard_data.get_actual_dashboard_metrics")
def test_rate_limiting_dashboard(mock_get_metrics):
    """Verify that calling the dashboard endpoint exceeds the rate limit after 10 requests."""
    from bff.fast_api_app import limiter

    limiter.reset()
    mock_get_metrics.return_value = {}

    try:
        # Call it 10 times (limit is 10/minute)
        for _ in range(10):
            response = client.get("/api/dashboard")
            assert response.status_code == 200

        # The 11th call should fail with a 429
        response_blocked = client.get("/api/dashboard")
        assert response_blocked.status_code == 429
        assert "rate limit exceeded" in response_blocked.json()["error"].lower()
    finally:
        # Clean up by resetting limiter
        limiter.reset()
