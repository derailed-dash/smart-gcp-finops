"""
Description: Unit tests for client initialisation and tool filtering logic in finops_agent.client.
Why: Ensures that BigQuery tool filtering guardrails correctly block raw SQL execution, forecasting, and querying tools while allowing approved custom tools.
How: Uses unittest/pytest primitives with Mock tool objects to test bq_tool_filter across allowed and disallowed tool names.
"""

from unittest.mock import MagicMock

from finops_agent.client import EXCLUDED_BQ_TOOL_KEYWORDS, bq_tool_filter


def test_excluded_bq_tool_keywords_set():
    """Verify that EXCLUDED_BQ_TOOL_KEYWORDS contains the expected filter keywords."""
    assert "execute" in EXCLUDED_BQ_TOOL_KEYWORDS
    assert "query" in EXCLUDED_BQ_TOOL_KEYWORDS
    assert "forecast" in EXCLUDED_BQ_TOOL_KEYWORDS
    assert "anomalies" in EXCLUDED_BQ_TOOL_KEYWORDS


def test_bq_tool_filter_allows_approved_tools():
    """Verify that approved tools without excluded keywords are allowed by bq_tool_filter."""
    mock_tool = MagicMock()
    mock_tool.name = "get_billing_account_metadata"
    assert bq_tool_filter(mock_tool) is True


def test_bq_tool_filter_blocks_disallowed_tools():
    """Verify that tools containing execute, query, forecast, or anomalies are blocked."""
    disallowed_names = [
        "execute_sql",
        "EXECUTE_QUERY",
        "run_bigquery_query",
        "bq_ml_forecast_tool",
        "detect_spend_anomalies",
    ]

    for tool_name in disallowed_names:
        mock_tool = MagicMock()
        mock_tool.name = tool_name
        assert bq_tool_filter(mock_tool) is False, f"Expected {tool_name} to be filtered out"
