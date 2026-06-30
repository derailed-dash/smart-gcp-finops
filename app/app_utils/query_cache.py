"""
Description: In-memory query caching manager.
Why: Reduces database invocation costs and latency by caching query outputs locally.
How: Implements a thread-safe dictionary with normalized SQL keys and expiration TTLs.
"""

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

def _normalise_sql(sql: str) -> str:
    """Normalises SQL formatting by compressing whitespace to standardise cache keys."""
    import re

    # Compress multiple whitespaces into a single space
    return re.sub(r"\s+", " ", sql).strip()


class QueryCacheManager:
    """Manages thread-safe in-memory caching of BigQuery query results."""

    def __init__(self) -> None:
        self._query_cache: dict[str, tuple[float, list[Any]]] = {}
        self._cache_lock = threading.Lock()

    def execute_cached_query(self, client: Any, sql: str, ttl_seconds: int = 300) -> list[Any]:
        """Executes a BigQuery SQL query with thread-safe in-memory caching to avoid table scans."""
        now = time.time()
        normalised_sql = _normalise_sql(sql)

        # Thread-safe read and expired cache cleanup
        with self._cache_lock:
            # Clean expired keys to prevent memory leaks over time
            expired_keys = [k for k, (expiry, _) in self._query_cache.items() if now > expiry]
            for k in expired_keys:
                del self._query_cache[k]

            if normalised_sql in self._query_cache:
                expiry, cached_rows = self._query_cache[normalised_sql]
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
        with self._cache_lock:
            self._query_cache[normalised_sql] = (now + ttl_seconds, rows)

        return rows

    def clear(self) -> None:
        """Clears all cached query results."""
        with self._cache_lock:
            self._query_cache.clear()
            logger.info("Query cache cleared successfully.")


# Module-level singleton instance for query caching management
query_cache_manager = QueryCacheManager()


def execute_cached_query(client: Any, sql: str, ttl_seconds: int = 300) -> list[Any]:
    """Executes a BigQuery SQL query with thread-safe in-memory caching to avoid table scans."""
    return query_cache_manager.execute_cached_query(client, sql, ttl_seconds)


def clear_query_cache() -> None:
    """Clears all cached query results. Useful for testing and manual invalidation."""
    query_cache_manager.clear()

