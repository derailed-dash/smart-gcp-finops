"""
Description: Custom application tools for the ADK agent.
Why: Isolates custom database tools and utility functions from agent orchestration.
How: Defines the cached BigQuery SQL execution tool using the Google BigQuery Python client.
"""

import logging
import re
import threading
from datetime import date, datetime
from decimal import Decimal

import google.auth
from google.adk import Context
from google.cloud import bigquery

from app.app_utils.context import ALLOWED_PROJECTS_VAR
from app.app_utils.query_cache import execute_cached_query
from app.config import settings

logger = logging.getLogger(__name__)


class BigQueryClientManager:
    """Manages thread-safe lazy-initialisation of the shared BigQuery client."""

    def __init__(self) -> None:
        self._bq_client = None
        self._bq_lock = threading.Lock()

    def get_client(self) -> bigquery.Client:
        """Returns the shared BigQuery client instance, building it if necessary."""
        if self._bq_client is None:
            with self._bq_lock:
                if self._bq_client is None:
                    credentials, _ = google.auth.default(
                        scopes=["https://www.googleapis.com/auth/bigquery"]
                    )
                    self._bq_client = bigquery.Client(
                        credentials=credentials,
                        project=settings.google_cloud_billing_project,
                    )
        return self._bq_client

    def reset(self) -> None:
        """Resets the cached BigQuery client."""
        with self._bq_lock:
            self._bq_client = None


# Module-level singleton instance for BigQuery client management
bq_client_manager = BigQueryClientManager()


def _get_bq_client() -> bigquery.Client:
    """Returns the shared BigQuery client instance, building it if necessary."""
    return bq_client_manager.get_client()



def _serialise_value(val):
    """Recursively serialises non-JSON-compliant data types (dates, decimals) for GenAI compatibility."""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    elif isinstance(val, Decimal):
        return float(val)
    elif isinstance(val, dict):
        return {k: _serialise_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_serialise_value(v) for v in val]
    return val


def execute_cached_bigquery_sql(sql: str, tool_context: Context) -> list[dict]:
    """Executes a BigQuery SQL query against the billing export tables.

    This tool is highly optimised and uses in-memory caching to avoid redundant,
    expensive database table scans and minimise query costs.
    """
    logger.info("Executing full BigQuery SQL query:\n%s", sql)
    try:
        user_email = tool_context.user_id
        if user_email:
            from app.app_utils.project_discovery import get_user_accessible_projects

            allowed_projects = get_user_accessible_projects(user_email)
        else:
            allowed_projects = ALLOWED_PROJECTS_VAR.get()
        if allowed_projects is not None:
            billing_suffix = settings.google_cloud_billing_account.replace("-", "_")
            standard_table = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_v1_{billing_suffix}"
            resource_table = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_resource_v1_{billing_suffix}"

            sanitized_projects = [p for p in allowed_projects if re.match(r"^[a-z0-9\-]+$", p)]
            if not sanitized_projects:
                subquery_standard = f"(SELECT * FROM `{standard_table}` LIMIT 0)"
                subquery_resource = f"(SELECT * FROM `{resource_table}` LIMIT 0)"
            else:
                proj_list = ", ".join(f"'{p}'" for p in sanitized_projects)
                subquery_standard = f"(SELECT * FROM `{standard_table}` WHERE project.id IN ({proj_list}))"
                subquery_resource = f"(SELECT * FROM `{resource_table}` WHERE project.id IN ({proj_list}))"

            escaped_std = re.escape(standard_table)
            pattern_std = re.compile(rf"`{escaped_std}`|{escaped_std}")
            sql = pattern_std.sub(subquery_standard, sql)

            escaped_res = re.escape(resource_table)
            pattern_res = re.compile(rf"`{escaped_res}`|{escaped_res}")
            sql = pattern_res.sub(subquery_resource, sql)

            logger.info("Scoped BigQuery SQL query:\n%s", sql)

        client = _get_bq_client()
        rows = execute_cached_query(client, sql)
        # Convert Row objects to standard, GenAI-serialisable dicts safely
        result = [{k: _serialise_value(v) for k, v in row.items()} for row in rows]
        logger.info("BigQuery returned %d rows.", len(result))
        if result:
            logger.info("Snippet of first 3 BQ results: %s", result[:3])
        return result
    except Exception as e:
        logger.error(f"Error in execute_cached_bigquery_sql tool: {e}", exc_info=True)
        return [{"error": str(e)}]
