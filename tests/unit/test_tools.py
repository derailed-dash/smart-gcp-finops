"""
Description: Unit tests for custom database tools.
Why: Validates that SQL query rewriting, caching, and project row-level security scoping filters prevent data leaks.
How: Sets up fixtures to mock BigQuery client executions and asserts query wrapping under various ALLOWED_PROJECTS_VAR scopes.
"""

from unittest.mock import MagicMock, patch

import pytest
from finops_agent.app_utils.context import ALLOWED_PROJECTS_VAR
from finops_agent.app_utils.tools import (
    execute_cached_bigquery_sql,
    get_precomputed_spend_analysis,
    get_today_top_services_and_usage,
    investigate_today_service_logs,
)


@pytest.fixture
def mock_settings():
    with patch("finops_agent.app_utils.tools.settings") as mock_set:
        mock_set.google_cloud_billing_project = "billing-proj"
        mock_set.billing_export_dataset = "billing_dataset"
        mock_set.google_cloud_billing_account = "123456-7890AB-CDEF01"
        yield mock_set


@pytest.fixture
def mock_bq_client():
    with patch("finops_agent.app_utils.tools._get_bq_client") as mock_get_client:
        client = MagicMock()
        mock_job = MagicMock()
        client.query.return_value = mock_job
        mock_job.result.return_value = []
        mock_get_client.return_value = client
        yield client


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.user_id = None
    ctx.state = {}
    return ctx


def test_execute_cached_bigquery_sql_no_restriction(mock_bq_client, mock_settings, mock_context):
    """Test that query is not modified when ALLOWED_PROJECTS_VAR is None (no restriction)."""
    token = ALLOWED_PROJECTS_VAR.set(None)
    try:
        mock_bq_client.query.return_value.result.return_value = [{"col1": "val1"}]
        sql = "SELECT * FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01`"
        res = execute_cached_bigquery_sql(sql, mock_context)
        assert res == [{"col1": "val1"}]
        mock_bq_client.query.assert_called_once_with(sql)
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_execute_cached_bigquery_sql_with_restriction(mock_bq_client, mock_settings, mock_context):
    """Test that query is rewritten to restrict projects to the user's allowed list."""
    token = ALLOWED_PROJECTS_VAR.set({"allowed-project-1", "allowed-project-2"})
    try:
        mock_bq_client.query.return_value.result.return_value = [{"col1": "val1"}]
        sql = "SELECT * FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01` WHERE cost > 0"
        res = execute_cached_bigquery_sql(sql, mock_context)
        assert res == [{"col1": "val1"}]

        called_sql = mock_bq_client.query.call_args[0][0]
        assert "project.id IN (" in called_sql
        assert "'allowed-project-1'" in called_sql
        assert "'allowed-project-2'" in called_sql
        assert "gcp_billing_export_v1_123456_7890AB_CDEF01" in called_sql
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_execute_cached_bigquery_sql_empty_allowed_projects(
    mock_bq_client, mock_settings, mock_context
):
    """Test that query is rewritten to return 0 rows (LIMIT 0) when user has no allowed projects."""
    token = ALLOWED_PROJECTS_VAR.set(set())
    try:
        mock_bq_client.query.return_value.result.return_value = []
        sql = "SELECT * FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01`"
        res = execute_cached_bigquery_sql(sql, mock_context)
        assert res == []
        called_sql = mock_bq_client.query.call_args[0][0]
        assert "LIMIT 0" in called_sql
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_execute_cached_bigquery_sql_agent_vs_user_visibility(
    mock_bq_client, mock_settings, mock_context
):
    """Test when agent can see more projects than the user (database contains other projects).

    The query must be forced to only search user's allowed projects, preventing the agent from
    accessing other projects' data even if the agent is querying the whole dataset.
    """
    token = ALLOWED_PROJECTS_VAR.set({"allowed-project-1"})
    try:
        mock_bq_client.query.return_value.result.return_value = []
        # Agent tries to run a query listing cost for all projects (e.g. GROUP BY project.id)
        sql = "SELECT project.id, SUM(cost) FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01` GROUP BY project.id"
        execute_cached_bigquery_sql(sql, mock_context)

        called_sql = mock_bq_client.query.call_args[0][0]
        # The query must be rewritten to wrap the table in a subquery that filters by allowed-project-1
        assert "project.id IN ('allowed-project-1')" in called_sql
        assert "'secret-project-1'" not in called_sql
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


@patch("finops_agent.app_utils.project_discovery.get_user_accessible_projects")
def test_execute_cached_bigquery_sql_dynamic_resolution(
    mock_get_projects, mock_bq_client, mock_settings
):
    """Test that query is rewritten using dynamically resolved allowed projects from user_id in the context."""
    mock_get_projects.return_value = {"allowed-project-1"}

    mock_context = MagicMock()
    mock_context.user_id = "user@dazbo.co.uk"
    mock_context.state = {}

    mock_bq_client.query.return_value.result.return_value = []
    sql = "SELECT * FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01`"

    execute_cached_bigquery_sql(sql, mock_context)

    mock_get_projects.assert_called_once_with("user@dazbo.co.uk")
    called_sql = mock_bq_client.query.call_args[0][0]
    assert "project.id IN ('allowed-project-1')" in called_sql


def test_execute_cached_bigquery_sql_session_caching(mock_bq_client, mock_settings, mock_context):
    """Verify that execute_cached_bigquery_sql caches query results in session state and skips BQ on subsequent runs."""
    token = ALLOWED_PROJECTS_VAR.set(None)
    try:
        sql = "SELECT SUM(cost) FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01`"

        # Configure BQ client to return different rows on subsequent calls to detect bypass
        mock_bq_client.query.return_value.result.side_effect = [
            [{"cost": 100.0}],
            [{"cost": 200.0}],
        ]

        # 1. First execution: Cache Miss -> should query BigQuery
        res1 = execute_cached_bigquery_sql(sql, mock_context)
        assert res1 == [{"cost": 100.0}]
        assert mock_bq_client.query.call_count == 1

        # 2. Second execution with same SQL: Cache Hit -> should return cached result, call_count remains 1
        res2 = execute_cached_bigquery_sql(sql, mock_context)
        assert res2 == [{"cost": 100.0}]
        assert mock_bq_client.query.call_count == 1
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_execute_cached_bigquery_sql_filter_pushdown(mock_bq_client, mock_settings, mock_context):
    """Verify that temporal and partition filters are parsed from the outer query and pushed down into the scoping subquery."""
    token = ALLOWED_PROJECTS_VAR.set({"allowed-project-1"})
    try:
        mock_bq_client.query.return_value.result.return_value = []
        sql = (
            "SELECT service.description, SUM(cost) "
            "FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01` "
            "WHERE export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) "
            "AND usage_start_time >= TIMESTAMP('2026-07-01') "
            "GROUP BY 1"
        )
        execute_cached_bigquery_sql(sql, mock_context)

        called_sql = mock_bq_client.query.call_args[0][0]

        # Check that the subquery standard table contains BOTH project scoping and the pushed-down date filters
        assert (
            "WHERE project.id IN ('allowed-project-1') AND export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) AND usage_start_time >= TIMESTAMP('2026-07-01')"
            in called_sql
        )
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_execute_cached_bigquery_sql_targeted_scoping(mock_bq_client, mock_settings, mock_context):
    """Verify that explicit project filters in the SQL are intersected with allowed_projects to narrow the scoping filter."""
    token = ALLOWED_PROJECTS_VAR.set(
        {"allowed-project-1", "allowed-project-2", "allowed-project-3"}
    )
    try:
        mock_bq_client.query.return_value.result.return_value = []

        # Scenario 1: Query specifies a single project that the user has access to
        sql1 = (
            "SELECT service.description, SUM(cost) "
            "FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01` "
            "WHERE project.id = 'allowed-project-2' "
            "GROUP BY 1"
        )
        execute_cached_bigquery_sql(sql1, mock_context)
        called_sql1 = mock_bq_client.query.call_args[0][0]
        # Should only scope to allowed-project-2 (intersection of {1,2,3} and {2})
        assert "project.id IN ('allowed-project-2')" in called_sql1
        assert "allowed-project-1" not in called_sql1

        # Scenario 2: Query specifies a project that the user does NOT have access to
        mock_bq_client.query.reset_mock()
        sql2 = (
            "SELECT service.description, SUM(cost) "
            "FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01` "
            "WHERE project.id = 'unauthorized-project' "
            "GROUP BY 1"
        )
        execute_cached_bigquery_sql(sql2, mock_context)
        called_sql2 = mock_bq_client.query.call_args[0][0]
        # Intersection is empty, should rewrite to LIMIT 0
        assert "LIMIT 0" in called_sql2
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_execute_cached_bigquery_sql_dynamic_routing(mock_bq_client, mock_settings, mock_context):
    """Verify that queries targeting the resource table are routed to the standard table if no resource properties are referenced."""
    token = ALLOWED_PROJECTS_VAR.set({"allowed-project-1"})
    try:
        mock_bq_client.query.return_value.result.return_value = []
        sql = (
            "SELECT MIN(DATE(usage_start_time)) "
            "FROM `billing-proj.billing_dataset.gcp_billing_export_resource_v1_123456_7890AB_CDEF01`"
        )
        execute_cached_bigquery_sql(sql, mock_context)
        called_sql = mock_bq_client.query.call_args[0][0]
        # Should have routed to the standard table instead of the resource table
        assert "gcp_billing_export_v1_123456_7890AB_CDEF01" in called_sql
        assert "gcp_billing_export_resource_v1" not in called_sql
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_execute_cached_bigquery_sql_defensive_temporal(
    mock_bq_client, mock_settings, mock_context
):
    """Verify that a default 90-day partition filter on export_time is defensively injected if no date filters are present."""
    token = ALLOWED_PROJECTS_VAR.set({"allowed-project-1"})
    try:
        mock_bq_client.query.return_value.result.return_value = []
        sql = (
            "SELECT project.id, SUM(cost) "
            "FROM `billing-proj.billing_dataset.gcp_billing_export_v1_123456_7890AB_CDEF01` "
            "GROUP BY 1"
        )
        execute_cached_bigquery_sql(sql, mock_context)
        called_sql = mock_bq_client.query.call_args[0][0]
        # Should have injected the 90-day export_time filter defensively into the subquery
        assert "export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY))" in called_sql
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_get_precomputed_spend_analysis_defaults(mock_bq_client, mock_settings, mock_context):
    """Verify that get_precomputed_spend_analysis generates 30/60 day intervals by default."""
    token = ALLOWED_PROJECTS_VAR.set(None)
    try:
        res = get_precomputed_spend_analysis(tool_context=mock_context)
        assert res["mtdChange"] == 100.0
        assert mock_bq_client.query.call_count == 3

        calls = [arg[0][0] for arg in mock_bq_client.query.call_args_list]
        # Daily service costs query
        assert "INTERVAL 30 DAY" in calls[0]
        # Period/MTD SKU spend query (uses days * 2 = 60)
        assert "INTERVAL 60 DAY" in calls[1]
        # Waste query
        assert "INTERVAL 30 DAY" in calls[2]
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)




def test_get_today_top_services_and_usage(mock_bq_client, mock_settings, mock_context):
    """Verify that get_today_top_services_and_usage queries INFORMATION_SCHEMA and updates state['today_top_services']."""
    token = ALLOWED_PROJECTS_VAR.set(None)
    try:
        mock_bq_client.query.return_value.result.return_value = [
            {"project_id": "test-project", "tb_billed": 0.5, "estimated_cost_usd": 3.12, "query_count": 5}
        ]
        res = get_today_top_services_and_usage(tool_context=mock_context)
        assert "top_services" in res
        assert len(res["top_services"]) > 0
        assert mock_context.state["today_top_services"] == res["top_services"]
    finally:
        ALLOWED_PROJECTS_VAR.reset(token)


def test_investigate_today_service_logs_with_blackboard(mock_context):
    """Verify that investigate_today_service_logs reads today_top_services from state if target_services is omitted."""
    mock_context.state["today_top_services"] = [
        {"service_name": "BigQuery", "gcp_service_id": "bigquery.googleapis.com"},
        {"service_name": "Vertex AI", "gcp_service_id": "aiplatform.googleapis.com"},
    ]
    with patch("google.auth.default", return_value=(MagicMock(), "test-proj")):
        with patch("google.cloud.logging.Client") as mock_logging:
            mock_client_inst = MagicMock()
            mock_client_inst.list_entries.return_value = []
            mock_logging.return_value = mock_client_inst

            res = investigate_today_service_logs(tool_context=mock_context)
            assert res["target_services"] == ["BigQuery", "Vertex AI"]
            assert "bigquery.googleapis.com" in res["log_filter"]
            assert "aiplatform.googleapis.com" in res["log_filter"]


def test_investigate_today_service_logs_detects_operational_anomaly(mock_context):
    """Verify that investigate_today_service_logs sets today_operational_anomaly when error log entries are returned."""
    mock_context.state["today_top_services"] = [
        {"service_name": "Cloud Run", "gcp_service_id": "run.googleapis.com"}
    ]

    mock_entry = MagicMock()
    mock_entry.severity = "ERROR"
    mock_entry.payload = {
        "serviceName": "run.googleapis.com",
        "methodName": "CreateRevision",
        "status": {"code": 13, "message": "Internal error scaling instances"},
        "authenticationInfo": {"principalEmail": "service-acc@proj.iam.gserviceaccount.com"},
    }

    with patch("google.auth.default", return_value=(MagicMock(), "test-proj")):
        with patch("google.cloud.logging.Client") as mock_logging:
            mock_client_inst = MagicMock()
            mock_client_inst.list_entries.return_value = [mock_entry]
            mock_logging.return_value = mock_client_inst

            res = investigate_today_service_logs(tool_context=mock_context)
            assert res["has_operational_anomaly"] is True
            assert res["error_count"] == 1
            assert mock_context.state["today_operational_anomaly"] is True
            assert len(mock_context.state["anomaly_details"]) == 1


