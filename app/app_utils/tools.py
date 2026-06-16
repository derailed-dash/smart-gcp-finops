"""
Description: Custom application tools for the ADK agent.
Why: Isolates custom database tools and utility functions from agent orchestration.
How: Defines the cached BigQuery SQL execution tool using the Google BigQuery Python client.
"""

import logging
import threading
from datetime import date, datetime
from decimal import Decimal

import google.auth
from google.cloud import bigquery

from app.app_utils.query_cache import execute_cached_query
from app.config import settings

logger = logging.getLogger(__name__)

# Thread-safe lazy-initialization of shared BigQuery Client
_bq_client = None
_bq_lock = threading.Lock()


def _get_bq_client():
    global _bq_client
    if _bq_client is None:
        with _bq_lock:
            if _bq_client is None:
                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/bigquery"]
                )
                _bq_client = bigquery.Client(
                    credentials=credentials,
                    project=settings.google_cloud_billing_project,
                )
    return _bq_client


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


def execute_cached_bigquery_sql(sql: str) -> list[dict]:
    """Executes a BigQuery SQL query against the billing export tables.

    This tool is highly optimised and uses in-memory caching to avoid redundant,
    expensive database table scans and minimise query costs.
    """
    logger.info("Executing full BigQuery SQL query:\n%s", sql)
    try:
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
