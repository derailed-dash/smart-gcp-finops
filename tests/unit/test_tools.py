"""
Description: Unit tests for custom database tools.
Why: Validates that SQL query rewriting, caching, and project row-level security scoping filters prevent data leaks.
How: Sets up fixtures to mock BigQuery client executions and asserts query wrapping under various ALLOWED_PROJECTS_VAR scopes.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.app_utils.context import ALLOWED_PROJECTS_VAR
from app.app_utils.tools import execute_cached_bigquery_sql


@pytest.fixture
def mock_settings():
    with patch("app.app_utils.tools.settings") as mock_set:
        mock_set.google_cloud_billing_project = "billing-proj"
        mock_set.billing_export_dataset = "billing_dataset"
        mock_set.google_cloud_billing_account = "123456-7890AB-CDEF01"
        yield mock_set

@pytest.fixture
def mock_bq_client():
    with patch("app.app_utils.tools._get_bq_client") as mock_get_client:
        client = MagicMock()
        mock_get_client.return_value = client
        yield client

@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.user_id = None
    return ctx


@patch("app.app_utils.tools.execute_cached_query")
def test_execute_cached_bigquery_sql_no_restriction(
    mock_execute_query, mock_bq_client, mock_settings, mock_context
):
    """Test that query is not modified when ALLOWED_PROJECTS_VAR is None (no restriction)."""
    token = ALLOWED_PROJECTS_VAR.set(None)
    try:
        mock_execute_query.return_value = [{"col1": "val1"}]
        sql = "SELECT * FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01`"
        res = execute_cached_bigquery_sql(sql, mock_context)
        assert res == [{"col1": "val1"}]
        mock_execute_query.assert_called_once_with(mock_bq_client, sql)
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


@patch("app.app_utils.tools.execute_cached_query")
def test_execute_cached_bigquery_sql_with_restriction(
    mock_execute_query, mock_bq_client, mock_settings, mock_context
):
    """Test that query is rewritten to restrict projects to the user's allowed list."""
    token = ALLOWED_PROJECTS_VAR.set({"allowed-project-1", "allowed-project-2"})
    try:
        mock_execute_query.return_value = [{"col1": "val1"}]
        sql = "SELECT * FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01` WHERE cost > 0"
        res = execute_cached_bigquery_sql(sql, mock_context)
        assert res == [{"col1": "val1"}]

        called_sql = mock_execute_query.call_args[0][1]
        assert "project.id IN (" in called_sql
        assert "'allowed-project-1'" in called_sql
        assert "'allowed-project-2'" in called_sql
        assert "gcp_billing_export_v1_123456_7890AB_CDEF01" in called_sql
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


@patch("app.app_utils.tools.execute_cached_query")
def test_execute_cached_bigquery_sql_empty_allowed_projects(
    mock_execute_query, mock_bq_client, mock_settings, mock_context
):
    """Test that query is rewritten to return 0 rows (LIMIT 0) when user has no allowed projects."""
    token = ALLOWED_PROJECTS_VAR.set(set())
    try:
        mock_execute_query.return_value = []
        sql = "SELECT * FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01`"
        res = execute_cached_bigquery_sql(sql, mock_context)
        assert res == []
        called_sql = mock_execute_query.call_args[0][1]
        assert "LIMIT 0" in called_sql
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


@patch("app.app_utils.tools.execute_cached_query")
def test_execute_cached_bigquery_sql_agent_vs_user_visibility(
    mock_execute_query, mock_bq_client, mock_settings, mock_context
):
    """Test when agent can see more projects than the user (database contains other projects).

    The query must be forced to only search user's allowed projects, preventing the agent from
    accessing other projects' data even if the agent is querying the whole dataset.
    """
    token = ALLOWED_PROJECTS_VAR.set({"allowed-project-1"})
    try:
        mock_execute_query.return_value = []
        # Agent tries to run a query listing cost for all projects (e.g. GROUP BY project.id)
        sql = "SELECT project.id, SUM(cost) FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01` GROUP BY project.id"
        execute_cached_bigquery_sql(sql, mock_context)

        called_sql = mock_execute_query.call_args[0][1]
        # The query must be rewritten to wrap the table in a subquery that filters by allowed-project-1
        assert "project.id IN ('allowed-project-1')" in called_sql
        assert "'secret-project-1'" not in called_sql
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


@patch("app.app_utils.project_discovery.get_user_accessible_projects")
@patch("app.app_utils.tools.execute_cached_query")
def test_execute_cached_bigquery_sql_dynamic_resolution(
    mock_execute_query, mock_get_projects, mock_bq_client, mock_settings
):
    """Test that query is rewritten using dynamically resolved allowed projects from user_id in the context."""
    mock_get_projects.return_value = {"allowed-project-1"}

    mock_context = MagicMock()
    mock_context.user_id = "user@dazbo.co.uk"

    mock_execute_query.return_value = []
    sql = "SELECT * FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01`"

    execute_cached_bigquery_sql(sql, mock_context)

    mock_get_projects.assert_called_once_with("user@dazbo.co.uk")
    called_sql = mock_execute_query.call_args[0][1]
    assert "project.id IN ('allowed-project-1')" in called_sql
