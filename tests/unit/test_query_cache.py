from unittest.mock import MagicMock

from finops_agent.app_utils.query_cache import (
    clear_query_cache,
    execute_cached_query,
)


def test_query_cache_hit_and_miss():
    """Verify that query caching registers a miss initially, hits subsequently, and respects TTL."""
    # Reset any existing cache states first
    clear_query_cache()

    # 1. Setup mock BigQuery client and query jobs
    mock_client = MagicMock()

    mock_job_1 = MagicMock()
    mock_row_1 = MagicMock()
    mock_row_1.cost = 100.0
    mock_job_1.result.return_value = [mock_row_1]

    mock_job_2 = MagicMock()
    mock_row_2 = MagicMock()
    mock_row_2.cost = 200.0
    mock_job_2.result.return_value = [mock_row_2]

    # Configure side effect to return different jobs on subsequent calls
    mock_client.query.side_effect = [mock_job_1, mock_job_2]

    sql = "SELECT SUM(cost) FROM test_table"

    # 2. First call: Cache Miss - should execute BigQuery query and cache result
    results_1 = execute_cached_query(mock_client, sql, ttl_seconds=10)
    assert len(results_1) == 1
    assert results_1[0].cost == 100.0
    assert mock_client.query.call_count == 1

    # 3. Second call within TTL: Cache Hit - should return cached rows without calling BigQuery
    results_2 = execute_cached_query(mock_client, sql, ttl_seconds=10)
    assert len(results_2) == 1
    assert results_2[0].cost == 100.0
    assert mock_client.query.call_count == 1  # Still 1 call

    # 4. Clear Cache explicitly and call again: Cache Miss - should execute again
    clear_query_cache()
    results_3 = execute_cached_query(mock_client, sql, ttl_seconds=10)
    assert len(results_3) == 1
    assert results_3[0].cost == 200.0
    assert mock_client.query.call_count == 2


def test_query_cache_ttl_expiry():
    """Verify that cached entries expire after the configured TTL window."""
    clear_query_cache()

    mock_client = MagicMock()

    mock_job_1 = MagicMock()
    mock_job_1.result.return_value = [{"cost": 10.0}]

    mock_job_2 = MagicMock()
    mock_job_2.result.return_value = [{"cost": 20.0}]

    mock_client.query.side_effect = [mock_job_1, mock_job_2]

    sql = "SELECT cost FROM my_table LIMIT 1"

    # Call with a tiny TTL (0 seconds/expired instantly)
    results_1 = execute_cached_query(mock_client, sql, ttl_seconds=-1)
    assert len(results_1) == 1
    assert results_1[0]["cost"] == 10.0
    assert mock_client.query.call_count == 1

    # The entry was immediately expired due to negative TTL, so next call is a cache miss
    results_2 = execute_cached_query(mock_client, sql, ttl_seconds=5)
    assert len(results_2) == 1
    assert results_2[0]["cost"] == 20.0
    assert mock_client.query.call_count == 2
