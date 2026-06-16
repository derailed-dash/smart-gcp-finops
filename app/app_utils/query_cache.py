import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Global thread-safe in-memory cache for BigQuery query results.
# Format: {query_string: (expiry_timestamp, list_of_rows)}
_QUERY_CACHE: dict[str, tuple[float, list[Any]]] = {}
_CACHE_LOCK = threading.Lock()


def _normalise_sql(sql: str) -> str:
    """Normalises SQL formatting by compressing whitespace to standardise cache keys."""
    import re

    # Compress multiple whitespaces into a single space
    return re.sub(r"\s+", " ", sql).strip()


def execute_cached_query(client: Any, sql: str, ttl_seconds: int = 300) -> list[Any]:
    """Executes a BigQuery SQL query with thread-safe in-memory caching to avoid table scans.

    This function implements caching to minimise expensive data scans and optimise response latency.
    """
    now = time.time()
    normalised_sql = _normalise_sql(sql)

    # Thread-safe read and expired cache cleanup
    with _CACHE_LOCK:
        # Clean expired keys to prevent memory leaks over time
        expired_keys = [k for k, (expiry, _) in _QUERY_CACHE.items() if now > expiry]
        for k in expired_keys:
            del _QUERY_CACHE[k]

        if normalised_sql in _QUERY_CACHE:
            expiry, cached_rows = _QUERY_CACHE[normalised_sql]
            if now <= expiry:
                logger.debug(
                    "Cache hit for query: %s...",
                    normalised_sql[:60],
                )
                return cached_rows

    # Cache miss - execute the actual BigQuery query
    logger.info("Cache miss for query: %s...", normalised_sql[:60])
    job = client.query(sql)
    rows = list(job.result())

    # Thread-safe write to cache
    with _CACHE_LOCK:
        _QUERY_CACHE[normalised_sql] = (now + ttl_seconds, rows)

    return rows


def clear_query_cache() -> None:
    """Clears all cached query results. Useful for testing and manual invalidation."""
    with _CACHE_LOCK:
        _QUERY_CACHE.clear()
        logger.info("Query cache cleared successfully.")
